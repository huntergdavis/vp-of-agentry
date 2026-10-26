const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const {formatCss,firstDifference}=require('./format-css.cjs');
const script=path.join(__dirname,'format-css.cjs');
test('check rejects a formatting difference without writing, and write is explicit',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'vp-css-format-'));
  try {
    const file=path.join(dir,'fixture.css'),source='a{color:red}\n';
    fs.writeFileSync(file,source);
    const check=spawnSync(process.execPath,[script,'--check',file],{cwd:dir,encoding:'utf8'});
    assert.equal(check.status,1);
    assert.match(check.stderr,/differs at line 1; no file written/);
    assert.equal(fs.readFileSync(file,'utf8'),source);
    const write=spawnSync(process.execPath,[script,'--write',file],{cwd:dir,encoding:'utf8'});
    assert.equal(write.status,0,write.stderr);
    assert.equal(fs.readFileSync(file,'utf8'),'a { color: red; }\n');
    const second=spawnSync(process.execPath,[script,'--check',file],{cwd:dir,encoding:'utf8'});
    assert.equal(second.status,0,second.stderr);
    assert.equal(JSON.parse(second.stdout).byteIdentical,true);
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
test('ordered CSS structure survives formatting and a declaration mutation is detected',()=>{
  const input='/* note */@media(min-width:1px){a,b{color:red!important;--x:2}}';
  const {after,evidence}=formatCss(input);
  assert.equal(evidence.normalizedAstEqual,true);
  assert.equal(evidence.negativeOneDeclarationDetected,true);
  assert.equal(formatCss(after).after,after);
  assert.notEqual(formatCss(after.replace('red','blue')).evidence.normalizedAstSha256,evidence.normalizedAstSha256);
  assert.equal(firstDifference(after,after.replace('red','blue')),3);
});
test('malformed CSS fails without replacing source',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'vp-css-invalid-'));
  try {
    const file=path.join(dir,'fixture.css'),source='a { color: red;';
    fs.writeFileSync(file,source);
    const result=spawnSync(process.execPath,[script,'--write',file],{encoding:'utf8'});
    assert.equal(result.status,1);
    assert.match(result.stderr,/CSS formatter:/);
    assert.equal(fs.readFileSync(file,'utf8'),source);
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
test('no mode defaults to a read-only check, including no arguments',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'vp-css-default-'));
  try {
    fs.mkdirSync(path.join(dir,'tools'));fs.mkdirSync(path.join(dir,'src'));
    fs.copyFileSync(script,path.join(dir,'tools/format-css.cjs'));
    fs.symlinkSync(path.resolve(__dirname,'../node_modules'),path.join(dir,'node_modules'),'dir');
    const file=path.join(dir,'src/style.css'),source='a{color:red}'+String.fromCharCode(10);
    fs.writeFileSync(file,source);
    for(const args of [[],[file]]) {
      const result=spawnSync(process.execPath,[path.join(dir,'tools/format-css.cjs'),...args],{cwd:dir,encoding:'utf8'});
      assert.equal(result.status,1);
      assert.match(result.stderr,/differs at line 1; no file written/);
      assert.equal(fs.readFileSync(file,'utf8'),source);
    }
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
