"""Optional UI smoke test against a running LOCAL development API.

Creates one escaped-HTML test incident and feedback/review records in your dev
workspace. Use an expendable database. Install .[browser] and a Playwright
Chromium browser first. --bridge is a harness for environments where browser
navigation is restricted; its SSE responses are buffered, not live-stream tested.
"""
from pathlib import Path
import argparse
import json
import uuid
import httpx
from playwright.sync_api import sync_playwright
from tracelens.config import Settings

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--bridge',action='store_true')
p.add_argument('--browser-executable',default=None)
p.add_argument('--base-url',default='http://127.0.0.1:8000')
a=p.parse_args();base=a.base_url.rstrip('/');token=Settings.from_env().token
checks=[]
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(executable_path=a.browser_executable,headless=True)
    page=browser.new_page(viewport={'width':1510,'height':1100},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    if a.bridge:
        def bridge(request):
            if not request['url'].startswith('/'):raise ValueError('Only local API paths are allowed in the harness')
            response=httpx.request(request.get('method','GET'),base+request['url'],headers=request.get('headers',{}),content=request.get('body'),timeout=60)
            return {'status':response.status_code,'headers':dict(response.headers),'body':response.text}
        page.expose_function('__apiBridge',bridge)
        page.evaluate("""() => {
          const storage=new Map(); Object.defineProperty(window,'sessionStorage',{value:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}});
          window.fetch=async(url,options={})=>{const r=await window.__apiBridge({url:String(url),method:options.method||'GET',headers:options.headers||{},body:options.body});return new Response(r.body,{status:r.status,headers:r.headers});};
          if(!crypto.randomUUID)crypto.randomUUID=()=> '10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(Number(c)^crypto.getRandomValues(new Uint8Array(1))[0]&15>>Number(c)/4).toString(16));
        }""")
        def mount():
            page.set_content('<!doctype html><html><head><title>TraceLens</title></head><body><div id="app"></div><div id="toast" role="status" aria-live="polite"></div><div id="evidence-dialog" class="dialog-backdrop" hidden></div></body></html>')
            page.add_style_tag(content=(root/'src/tracelens/static/style.css').read_text())
            core=(root/'src/tracelens/static/core.mjs').read_text().replace('export ','')
            script=(root/'src/tracelens/static/dashboard.js').read_text().split('\n',1)[1]
            page.evaluate('(()=>{'+core+'\nconst e=escapeHtml;\n'+script+'\n})()')
        mount()
    else:
        def mount():page.reload(wait_until='networkidle')
        page.goto(base,wait_until='networkidle')
    page.get_by_label('Local API token').fill(token)
    page.get_by_role('button',name='Open workspace').click()
    page.get_by_role('heading',name='Incident workspace').wait_for();checks.append('Login and authorized incident loading')
    page.get_by_role('button',name='New investigation').click()
    page.get_by_role('button',name='Looks right').wait_for(timeout=20000);checks.append('ML ranking and investigation result rendering')
    page.screenshot(path=str(root/'docs/dashboard.png'),full_page=True)
    page.locator('[data-evidence]').first.click();page.get_by_role('dialog').wait_for();checks.append('Source evidence inspection')
    page.get_by_role('button',name='Close').click()
    page.get_by_role('button',name='Looks right').click();page.get_by_role('status').filter(has_text='Feedback saved').wait_for();checks.append('Feedback persistence')
    page.on('dialog',lambda dialog:dialog.accept('Reviewed in local browser smoke test'))
    page.get_by_role('button',name='Record human review').click();page.get_by_role('status').filter(has_text='Human review recorded').wait_for();checks.append('Non-executing human review')
    page.locator('[data-tab="activity"]').click();page.get_by_text('get_service_metrics',exact=True).first.wait_for();checks.append('Tool activity trace')
    page.locator('[data-page="evaluation"]').click();page.get_by_text('gradient_boosting',exact=True).wait_for();checks.append('Measured evaluation dashboard')
    page.screenshot(path=str(root/'docs/evaluation.png'),full_page=True)
    page.locator('[data-page="audit"]').click();page.get_by_text('human_review_recorded',exact=True).first.wait_for();checks.append('Review audit trail')
    page.locator('[data-page="investigate"]').click();page.locator('[data-tab="diagnosis"]').click()
    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(root/'docs/mobile.png'),full_page=True)
    dimensions=page.evaluate('({viewport:innerWidth,document:document.documentElement.scrollWidth})')
    assert dimensions['document']<=dimensions['viewport']+1,dimensions
    checks.append('Mobile layout without horizontal overflow')
    raw=json.loads((root/'examples/incident.json').read_text());raw['id']='ui-xss-'+uuid.uuid4().hex[:10]
    raw['title']='<img src=x onerror="window.__xss=1">';raw['logs'][0]['message']='<script>window.__xss=1</script>'
    response=httpx.post(base+'/api/incidents',headers={'Authorization':'Bearer '+token},json=raw);response.raise_for_status()
    page.set_viewport_size({'width':1510,'height':1100});mount();page.locator(f'[data-incident="{raw["id"]}"]').click()
    assert page.evaluate('window.__xss ?? null') is None;checks.append('Imported telemetry HTML is escaped')
    assert not errors,errors;browser.close()
report={'frontend':'Bundled no-Node dashboard, not the Next.js application','browser':'Chromium / Playwright',
        'transport':'Real API via Python HTTP bridge; SSE buffered' if a.bridge else 'Direct browser navigation and fetch',
        'checks':checks,'passed':len(checks),'uncaught_javascript_errors':errors,'mobile_dimensions':dimensions}
(root/'reports/browser-smoke.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
