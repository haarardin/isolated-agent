package main

import (
 "bufio"
 "bytes"
 "context"
 "encoding/json"
 "errors"
 "flag"
 "fmt"
 "io"
 "net/http"
 "net/url"
 "os"
 "os/signal"
 "strings"
 "time"
)

type apiClient struct {
 base string
 key string
 http *http.Client
}

func (c apiClient) call(ctx context.Context, method, path string, body any, key string) ([]byte,error) {
 var input io.Reader
 if body!=nil {
  data,err:=json.Marshal(body); if err!=nil{return nil,err}
  input=bytes.NewReader(data)
 }
 req,err:=http.NewRequestWithContext(ctx,method,strings.TrimSuffix(c.base,"/")+path,input)
 if err!=nil{return nil,err}
 req.Header.Set("Authorization","Bearer "+c.key)
 req.Header.Set("OpenAI-Beta","agents=v1")
 if body!=nil{req.Header.Set("Content-Type","application/json")}
 if key!=""{req.Header.Set("Idempotency-Key",key)}
 resp,err:=c.http.Do(req);if err!=nil{return nil,err}
 defer resp.Body.Close()
 output,err:=io.ReadAll(io.LimitReader(resp.Body,1<<20));if err!=nil{return nil,err}
 if resp.StatusCode<200||resp.StatusCode>=300 {
  return nil,fmt.Errorf("Agents API HTTP %d: %s",resp.StatusCode,strings.TrimSpace(string(output)))
 }
 return output,nil
}

func validID(id string) bool {
 if len(id)==0||len(id)>128{return false}
 for _,r:=range id {
  if r>='a'&&r<='z'||r>='A'&&r<='Z'||r>='0'&&r<='9'||r=='_'||r=='-'{continue}
  return false
 }
 return true
}

func (c apiClient) create(ctx context.Context,model,instructions string) ([]byte,error) {
 request:=map[string]any{
  "agent":map[string]any{"model":model,"instructions":instructions},
  "environment":map[string]any{"type":"self_hosted","workspace_directory":"/workspace"},
 }
 data,err:=c.call(ctx,"POST","/agents/sessions",request,"")
 if err!=nil{return nil,err}
 var payload struct {
  ID string
  Environment map[string]any
 }
 if err=json.Unmarshal(data,&payload);err!=nil{return nil,err}
 if payload.ID==""||payload.Environment["id"]==nil||payload.Environment["remote_url"]==nil{
  return nil,errors.New("missing session id or self-hosted environment connection details")
 }
 return data,nil
}

func (c apiClient) send(ctx context.Context,id,message,key string) error {
 if !validID(id){return errors.New("invalid session ID")}
 if strings.TrimSpace(message)==""{return errors.New("message cannot be empty")}
 if strings.TrimSpace(key)==""{return errors.New("--idempotency-key required; reuse on retry")}
 payload:=map[string]any{"events":[]any{map[string]any{
  "type":"agent.session.input.message",
  "input":[]any{map[string]any{"role":"user","content":[]any{
   map[string]any{"type":"input_text","text":message},
  }}},
 }}}
 _,err:=c.call(ctx,"POST","/agents/sessions/"+id+"/events",payload,key)
 return err
}

func (c apiClient) status(ctx context.Context,id string) ([]byte,error) {
 if !validID(id){return nil,errors.New("invalid session ID")}
 return c.call(ctx,"GET","/agents/sessions/"+id,nil,"")
}

func (c apiClient) watch(ctx context.Context,id string,out io.Writer) error {
 if !validID(id){return errors.New("invalid session ID")}
 req,err:=http.NewRequestWithContext(ctx,"GET",strings.TrimSuffix(c.base,"/")+"/agents/sessions/"+id+"/events",nil)
 if err!=nil{return err}
 req.Header.Set("Authorization","Bearer "+c.key)
 req.Header.Set("OpenAI-Beta","agents=v1")
 req.Header.Set("Accept","text/event-stream")
 client:=*c.http
 client.Timeout=0
 resp,err:=client.Do(req);if err!=nil{return err}
 defer resp.Body.Close()
 if resp.StatusCode!=200{return fmt.Errorf("event stream returned HTTP %d",resp.StatusCode)}
 scan:=bufio.NewScanner(resp.Body)
 scan.Buffer(make([]byte,4096),4<<20)
 for scan.Scan() {
  line:=scan.Text()
  if strings.HasPrefix(line,"data:") {
   fmt.Fprintln(out,strings.TrimSpace(strings.TrimPrefix(line,"data:")))
  }
 }
 return scan.Err()
}

func run(ctx context.Context,args []string,c apiClient,out io.Writer) error {
 if len(args)==0{return errors.New("usage: remote-session create|send|status|watch [flags]")}
 switch args[0] {
 case "create":
  f:=flag.NewFlagSet("create",flag.ContinueOnError)
  model:=f.String("model","gpt-6-astra","Agents API model")
  instructions:=f.String("instructions","Work only in /workspace. Run tests and report actual results.","agent instructions")
  if err:=f.Parse(args[1:]);err!=nil{return err}
  if f.NArg()!=0{return errors.New("unexpected arguments")}
  data,err:=c.create(ctx,*model,*instructions)
  if err!=nil{return err}
  _,err=fmt.Fprintln(out,string(data));return err
 case "send":
  f:=flag.NewFlagSet("send",flag.ContinueOnError)
  id:=f.String("session","","session ID")
  msg:=f.String("text","","task text")
  key:=f.String("idempotency-key","","stable key per logical message")
  if err:=f.Parse(args[1:]);err!=nil{return err}
  if f.NArg()!=0{return errors.New("unexpected arguments")}
  if err:=c.send(ctx,*id,*msg,*key);err!=nil{return err}
  _,err:=fmt.Fprintln(out,"Input accepted (not yet completed).");return err
 case "status","watch":
  f:=flag.NewFlagSet(args[0],flag.ContinueOnError)
  id:=f.String("session","","session ID")
  if err:=f.Parse(args[1:]);err!=nil{return err}
  if f.NArg()!=0{return errors.New("unexpected arguments")}
  if args[0]=="watch"{return c.watch(ctx,*id,out)}
  data,err:=c.status(ctx,*id);if err!=nil{return err}
  var b bytes.Buffer
  if json.Indent(&b,data,"","  ")==nil{data=b.Bytes()}
  _,err=fmt.Fprintln(out,string(data));return err
 default:return errors.New("unknown subcommand")
 }
}

func main() {
 key:=os.Getenv("OPENAI_API_KEY")
 if key==""{fmt.Fprintln(os.Stderr,"OPENAI_API_KEY must be set on the host");os.Exit(2)}
 base:="https://api.openai.com/v1"
 if v:=os.Getenv("OPENAI_API_BASE_URL");v!=""{
  u,err:=url.Parse(v)
  if err!=nil||u.Scheme!="https"{fmt.Fprintln(os.Stderr,"custom API base must use HTTPS");os.Exit(2)}
  base=v
 }
 ctx,stop:=signal.NotifyContext(context.Background(),os.Interrupt);defer stop()
 client:=apiClient{base:base,key:key,http:&http.Client{Timeout:45*time.Second}}
 if err:=run(ctx,os.Args[1:],client,os.Stdout);err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}
}
