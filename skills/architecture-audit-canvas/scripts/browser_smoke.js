// Playwright CLI run-code file. Open the generated HTML first; no fixed port/path.
async page => {
  const checks={},errors=[],requests=[];
  await page.setViewportSize({width:1680,height:1050});
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
  const check=(name,value)=>{checks[name]=!!value;if(!value)throw Error(name)};
  const state=()=>page.evaluate(()=>window.ARCH_AUDIT.getState());
  await page.locator('#viewList [data-view]').first().waitFor();
  const expected=await page.evaluate(()=>({views:DATA.views.length,modules:DATA.modules.length,risks:DATA.findings.length,questions:DATA.questions.length,snapshot:DATA.meta.snapshotId}));
  check('dynamic_view_count',await page.locator('#viewList [data-view]').count()===expected.views);
  check('dynamic_module_count',await page.locator('#moduleList [data-module]').count()===expected.modules);
  for(let i=0;i<expected.views;i++){await page.locator('#viewList [data-view]').nth(i).click();check('view_'+i,(await state()).visibleNodes>0)}
  await page.locator('#viewList [data-view]').first().click();await page.locator('#fitBtn').click();
  const base=await state();await page.locator('#zoomIn').click();check('zoom_in',(await state()).transform.k>base.transform.k);await page.locator('#zoomOut').click();
  const box=await page.locator('#graph').boundingBox(),before=await state();
  await page.mouse.move(box.x+10,box.y+10);await page.mouse.down();await page.mouse.move(box.x+90,box.y+60,{steps:5});await page.mouse.up();
  check('pan',Math.abs((await state()).transform.x-before.transform.x)>50);
  await page.locator('#fitBtn').click();await page.locator('.node').first().click();
  check('node_details',(await page.locator('#detailBody').innerText()).length>20);
  if(await page.locator('#detailBody [data-ref-index]').count()){
    await page.locator('#detailBody [data-ref-index]').first().click();check('source_snippet',await page.locator('#sourceBox .code-line').count()>0);
  }
  await page.locator('#startTrace').click();
  if(await page.locator('[data-step]').count()){
    await page.locator('[data-step]').first().click();check('trace_step',(await state()).trace.length===2);
    await page.locator('#traceBack').click();check('trace_back',(await state()).trace.length===1);
  }
  if(await page.locator('.edge').count()){
    await page.locator('.edge').first().press('Enter');check('edge_evidence',(await page.locator('#detailBody').innerText()).includes('这条边的证据'));
  }
  const module=await page.evaluate(()=>DATA.modules.find(m=>m.symbols.length)?.path||DATA.modules[0]?.path);
  if(module){
    await page.locator('#moduleSearch').fill(module);await page.locator('[data-module]').first().click();
    check('module_drilldown',(await state()).route.type==='module');
    if(await page.locator('[data-symbol]').count()){
      await page.locator('[data-symbol]').first().click();await page.locator('#fullSymbol').click();check('symbol_evidence',await page.locator('#sourceBox .code-line').count()>0);
    }
    await page.locator('#moduleSearch').fill('');await page.locator('#backBtn').click();check('back_navigation',(await state()).route.type==='view');
  }
  await page.locator('#risksBtn').click();check('risk_count',await page.locator('[data-list-risk]').count()===expected.risks);
  await page.locator('#questionsBtn').click();check('question_count',await page.locator('[data-question]').count()===expected.questions);
  await page.locator('#aboutBtn').click();check('coverage_and_limits',(await page.locator('#contentPanel').innerText()).includes('已审查'));
  await page.locator('#viewList [data-view]').first().click();await page.locator('#fitBtn').click();
  await page.screenshot({path:'canvas-desktop.png'});
  await page.setViewportSize({width:390,height:844});check('narrow_no_overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#navToggle').click();await page.locator('#viewList [data-view]').first().click();await page.locator('#detailToggle').click();
  check('narrow_evidence_panel',await page.locator('#detail').evaluate(e=>e.classList.contains('open')));
  await page.screenshot({path:'canvas-narrow.png'});
  const html=await page.content();await page.goto('about:blank');await page.setViewportSize({width:1680,height:1050});let attempts=0;
  await page.route('**/*',r=>{attempts++;return r.abort()});await page.setContent(html,{waitUntil:'load'});
  await page.locator('#viewList [data-view]').first().waitFor();check('offline_boot',await page.locator('[data-module]').count()===expected.modules);
  check('zero_offline_network',attempts===0);check('no_script_errors',errors.length===0);
  check('no_external_requests',requests.every(u=>u==='about:blank'||u.startsWith('http://127.0.0.1:')||u.startsWith('file:')));
  return {checks,errors,offline_requests:attempts,snapshot_id:expected.snapshot};
}
