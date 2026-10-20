/** Supplemental syntax-only check. Run npm run typecheck/build for full validation. */
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
let ts;
try {
  ts = createRequire(path.join(root, 'web', 'package.json'))('typescript');
} catch {
  ts = require(process.env.TYPESCRIPT_MODULE || 'typescript');
}
function walk(dir) {
  return fs.readdirSync(dir, {withFileTypes:true}).flatMap(e => {
    if (['node_modules','.next'].includes(e.name)) return [];
    const p = path.join(dir,e.name);
    return e.isDirectory() ? walk(p) : /\.tsx?$/.test(e.name) && !e.name.endsWith('.d.ts') ? [p] : [];
  });
}
const files = walk(path.join(root,'web'));
const errors = [];
for (const file of files) {
  const result = ts.transpileModule(fs.readFileSync(file,'utf8'),{
    fileName:file,
    compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX,strict:true},
    reportDiagnostics:true,
  });
  for (const diagnostic of result.diagnostics || []) {
    if(diagnostic.category === ts.DiagnosticCategory.Error) {
      errors.push({file:path.relative(root,file),message:ts.flattenDiagnosticMessageText(diagnostic.messageText,'\n')});
    }
  }
}
const report={check:'TypeScript/TSX syntax transpilation only; NOT full React/Next type checking or a production build',compiler:ts.version,files:files.length,errors};
fs.writeFileSync(path.join(root,'reports','frontend-syntax.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
process.exitCode=errors.length ? 1 : 0;
