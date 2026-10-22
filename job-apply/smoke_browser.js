/* Smoke runs on an independent temporary browser profile, not the login profile. */
const {createRequire} = require('node:module');
const fs = require('node:fs');
const {pathToFileURL} = require('node:url');
const fromMcp = createRequire('/usr/local/lib/node_modules/@playwright/mcp/package.json');
const {chromium} = fromMcp('playwright');
(async () => {
  const browser = await chromium.launch({
    executablePath: '/usr/bin/chromium', headless: true, args: ['--no-sandbox']
  });
  try {
    const page = await browser.newPage();
    await page.goto('https://example.com/', {waitUntil: 'domcontentloaded', timeout: 30000});
    const heading = await page.locator('h1').first().innerText();
    if (!heading.includes('Example Domain')) throw new Error('Unexpected example.com title: ' + heading);
    await page.screenshot({path:'/workspace/captures/example-screenshot.png'});
    await page.goto(pathToFileURL('/opt/jobapply/test-form.html').href);
    await page.getByLabel('Full name').fill('Test Candidate');
    await page.getByLabel('Email').fill('test@example.com');
    await page.getByLabel('Resume').setInputFiles('/workspace/applications/__smoke__/smoke.pdf');
    if (await page.getByLabel('Full name').inputValue() !== 'Test Candidate')
      throw new Error('Local form fill failed');
    if (await page.getByLabel('Resume').evaluate(e => e.files.length) !== 1)
      throw new Error('Local file upload failed');
    await page.screenshot({path:'/workspace/captures/local-application-form.png'});
    // Do not click the test submit button; never send to external ATS.
    console.log('BROWSER SMOKE OK: example.com and local form, never submitted');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
