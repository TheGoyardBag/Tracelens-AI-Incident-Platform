export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const percent = value => `${(Number(value) * 100).toFixed(1)}%`;
export function parseEvents(buffer) {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const blocks = normalized.split('\n\n');
  const rest = blocks.pop() || '';
  const events = [];
  for (const block of blocks) {
    const lines = block.split('\n');
    const data = lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n');
    if (!data) continue;
    const name = lines.find(l => l.startsWith('event:'))?.slice(6).trim() || 'message';
    const id = lines.find(l => l.startsWith('id:'))?.slice(3).trim() || '';
    events.push({ name, id, data: JSON.parse(data) });
  }
  return { events, rest };
}
export function chartPoints(values, width=420, height=100) {
  if (!values.length) return '';
  const safe=values.map(v=>Number.isFinite(Number(v)) ? Number(v) : 0);
  const max=Math.max(.02,...safe), min=0;
  return safe.map((v,i)=>`${(i*width/Math.max(1,safe.length-1)).toFixed(2)},${(height-(v-min)/Math.max(.001,max-min)*height).toFixed(2)}`).join(' ');
}
