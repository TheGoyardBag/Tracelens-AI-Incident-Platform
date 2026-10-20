import test from 'node:test';
import assert from 'node:assert/strict';
import {escapeHtml,parseEvents,chartPoints,percent} from '../src/tracelens/static/core.mjs';
test('escaped telemetry cannot become HTML',()=>assert.equal(escapeHtml('<img src=x onerror="evil()">'), '&lt;img src=x onerror=&quot;evil()&quot;&gt;'));
test('SSE parses a completed event and retains a partial record',()=>{
 const a=parseEvents('id: 4\nevent: step\ndata: {"kind":"tool"}\n\nevent: done\nda');
 assert.equal(a.events.length,1);assert.equal(a.events[0].id,'4');assert.equal(a.events[0].data.kind,'tool');assert.equal(a.rest,'event: done\nda');
});
test('SSE handles heartbeat and CRLF',()=>{
 const p=parseEvents(': ping\r\n\r\nevent: done\r\ndata: {}\r\n\r\n');
 assert.equal(p.events.length,1);assert.equal(p.events[0].name,'done');
});
test('SSE supports multi-line JSON',()=>assert.equal(parseEvents('data: {\ndata: "x": 2}\n\n').events[0].data.x,2));
test('SSE preserves partial frames until a delimiter',()=>assert.equal(parseEvents('event: step\ndata: {}').events.length,0));
test('chart handles empty and degenerate arrays',()=>{assert.equal(chartPoints([]),'');assert.equal(chartPoints([0]),'0.00,100.00');});
test('chart never embeds non-numeric content',()=>{assert.ok(!chartPoints(['<script>',1]).includes('<'));});
test('probability formatting',()=>assert.equal(percent(.8123),'81.2%'));
