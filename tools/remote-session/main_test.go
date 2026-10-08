package main

import (
 "bytes"
 "context"
 "encoding/json"
 "net/http"
 "net/http/httptest"
 "strings"
 "testing"
)

func TestCreate(t *testing.T) {
 srv:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request) {
  if r.Method!="POST"||r.URL.Path!="/agents/sessions"{t.Errorf("unexpected API request %s %s",r.Method,r.URL.Path)}
  if r.Header.Get("Authorization")!="Bearer fake"||r.Header.Get("OpenAI-Beta")!="agents=v1"{t.Error("missing auth/beta header")}
  var payload map[string]any
  if err:=json.NewDecoder(r.Body).Decode(&payload);err!=nil{t.Fatal(err)}
  env:=payload["environment"].(map[string]any)
  if env["type"]!="self_hosted"||env["workspace_directory"]!="/workspace"{t.Errorf("wrong environment: %v",env)}
  w.Header().Set("Content-Type","application/json")
  w.Write([]byte("{\"id\":\"sess_test\",\"environment\":{\"id\":\"env_test\",\"remote_url\":\"https://api.openai.com/v1/agents/api\"}}"))
 }))
 defer srv.Close()
 c:=apiClient{base:srv.URL,key:"fake",http:srv.Client()}
 result,err:=c.create(context.Background(),"gpt-6-astra","safe")
 if err!=nil||!bytes.Contains(result,[]byte("env_test")){t.Fatalf("create %s %v",result,err)}
}

func TestSendAndIdempotency(t *testing.T) {
 srv:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request) {
  if r.URL.Path!="/agents/sessions/sess_test/events"{t.Errorf("unexpected path %s",r.URL.Path)}
  if r.Header.Get("Idempotency-Key")!="msg-123"{t.Error("missing idempotency header")}
  var data map[string]any
  if err:=json.NewDecoder(r.Body).Decode(&data);err!=nil{t.Fatal(err)}
  events:=data["events"].([]any)
  event:=events[0].(map[string]any)
  if event["type"]!="agent.session.input.message"{t.Errorf("wrong event: %v",event)}
  w.WriteHeader(http.StatusAccepted)
 }))
 defer srv.Close()
 c:=apiClient{base:srv.URL,key:"fake",http:srv.Client()}
 if err:=c.send(context.Background(),"sess_test","test prompt","msg-123");err!=nil{t.Fatal(err)}
 if err:=c.send(context.Background(),"../secret","oops","msg-123");err==nil{t.Fatal("accepted invalid ID")}
 if err:=c.send(context.Background(),"sess_test","test prompt","");err==nil{t.Fatal("accepted missing idempotency key")}
}

func TestWatch(t *testing.T) {
 srv:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request) {
  w.Header().Set("Content-Type","text/event-stream")
  w.Write([]byte("event: state\ndata: {\"type\":\"agent.session.environment.connected\"}\n\n"))
 }))
 defer srv.Close()
 c:=apiClient{base:srv.URL,key:"fake",http:srv.Client()}
 var out bytes.Buffer
 if err:=c.watch(context.Background(),"sess_test",&out);err!=nil{t.Fatal(err)}
 if !strings.Contains(out.String(),"environment.connected"){t.Fatal(out.String())}
}

func TestStatusRejectsBadSession(t *testing.T) {
 c:=apiClient{base:"https://unused.invalid/v1",key:"fake",http:http.DefaultClient}
 if _,err:=c.status(context.Background(),"../invalid");err==nil{t.Fatal("accepted traversal")}
}
