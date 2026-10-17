/* Later official-source corrections. The original research datasets stay intact. */
function sourceUpdatesFor(id){return (window.SOURCE_UPDATES?.updates||[]).filter(update=>update.company_id===id);}
function sourceUpdateUnknownText(id,original){
 return id==='elorian'&&sourceUpdatesFor(id).some(update=>update.id==='elorian-platform-availability-2026-10-16')?'Private pilot traction, revenue, commercial customers and availability beyond the research preview.':original;
}
function applyProductSourceUpdates(id,rows){
 const updates=sourceUpdatesFor(id);if(!updates.length)return rows;
 return rows.map(product=>{
  const matched=updates.filter(update=>update.target.product_name===product.name&&update.target.record_ids.every(record=>product.record_ids?.includes(record))&&update.target.claim_ids.every(claim=>product.claim_ids?.includes(claim)));
  return matched.length?Object.assign({},product,...matched.map(update=>update.replacement_fields),{source_updates:matched}):product;
 });
}
function sourceUpdateReferenceHTML(update,label='Company source'){
 return `<span class="source-update-reference" data-source-update="${attr(update.id)}">${external(update.source.url,label)}<span class="sub">Checked ${esc(profileDate(update.source.observed_on))}</span></span>`;
}
function productSourceHTML(product,label='Source',topic=''){
 return product.source_updates?.length?product.source_updates.map(update=>sourceUpdateReferenceHTML(update,label==='Source'?'Company source':label)).join(' '):profileReferences(product.claim_ids,label,topic);
}
function productSourceContextHTML(product){
 if(!product.source_updates?.length)return '';
 return `<details class="offering-aliases source-update-context"><summary>Source update context</summary>${product.source_updates.map(update=>`<p>${esc(update.qualification)}</p>${update.supporting_sources.map(source=>`<p>${external(source.url,source.title)} · Checked ${esc(profileDate(source.observed_on))}</p>`).join('')}`).join('')}<p><a href="source-updates.json" download>Source updates · JSON</a></p></details>`;
}
function sourceUpdatesArchiveHTML(id){
 const updates=sourceUpdatesFor(id);if(!updates.length)return '';
 return `<div class="source-update-note" data-source-updates-company="${attr(id)}"><p>Records below retain the original dataset ${esc(window.SOURCE_UPDATES.baseline_dataset_version)} context. Current product descriptions include later source corrections.</p><p>${updates.map(update=>sourceUpdateReferenceHTML(update,update.target.product_name)).join(' ')}</p><p><a href="source-updates.json" download>Source updates and prior values · JSON</a></p></div>`;
}
function sourceUpdateClaimHTML(id){
 const updates=(window.SOURCE_UPDATES?.updates||[]).filter(update=>update.affected_claim_ids.includes(id));if(!updates.length)return '';
 return `<aside class="source-update-note" data-source-update-claim="${attr(id)}"><p><strong>Later product source update</strong></p>${updates.map(update=>`<p>${esc(update.replacement_fields.description)}${update.replacement_fields.status?' '+esc(update.replacement_fields.status)+'.':''}</p>${sourceUpdateReferenceHTML(update)}<p class="sub">${esc(update.qualification)}</p>`).join('')}<p class="sub">The original dataset ${esc(window.SOURCE_UPDATES.baseline_dataset_version)} statement and evidence remain below.</p></aside>`;
}

// Context corrections never replace canonical metrics, claims or source lists.
function evidenceContextSnapshotMatches(actual,expected){
 return Boolean(actual&&expected&&Object.keys(expected).every(key=>JSON.stringify(actual[key])===JSON.stringify(expected[key])));
}
function relationshipAssessmentContextValid(update){
 const keys=(value,expected)=>Boolean(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===expected.length&&expected.every(key=>Object.hasOwn(value,key)));
 const exact=(actual,expected)=>Boolean(actual&&expected&&typeof expected==='object'&&!Array.isArray(expected)&&Object.keys(actual).length===Object.keys(expected).length&&evidenceContextSnapshotMatches(actual,expected));
 const fields=['id','kind','company_id','reviewed_on','checked_at','review_basis','target','affected_claim_ids','display_scope','context','relationship_context','assessment_context','criterion_context','sources','historical_snapshot'];
 if(!keys(update,fields)||update.id!=='terac-dialogue-assessment-scope-2026-10-17'||update.company_id!=='terac'||update.kind!=='relationship-assessment-scope-context')return false;
 if(update.reviewed_on!=='2026-10-17'||update.reviewed_on>new Date().toISOString().slice(0,10)||update.checked_at!==null||update.review_basis!=='retained_public_evidence'||update.display_scope!=='Market research')return false;
 const claimIds=['terac.claim.customers-0',...['p','c','r'].map(key=>'terac.claim.assessment-evidence-'+key)],sourceIds=['terac.source.terac-4','terac.source.terac-1','terac.source.terac-2','terac.source.terac-7'];
 if(!exact(update.target,{claim_id:claimIds[0],customer_record_id:'terac.customer.0',assessment_id:'terac.assessment.ai_data'})||JSON.stringify(update.affected_claim_ids)!==JSON.stringify(claimIds)||!keys(update.criterion_context,['P','C','R']))return false;
 if(![update.context,update.relationship_context,update.assessment_context,...Object.values(update.criterion_context)].every(value=>typeof value==='string'&&value.trim()&&!/[<>\x00-\x1f]/.test(value)))return false;
 const snapshot=update.historical_snapshot;
 if(!keys(snapshot,['dataset_version','metrics','claims','sources','assessments','customer_evidence','profile_relationships'])||snapshot.dataset_version!=='2.5.0'||snapshot.dataset_version!==DATA.dataset_version||!Array.isArray(snapshot.metrics)||snapshot.metrics.length)return false;
 for(const [table,ids]of [['claims',claimIds],['sources',sourceIds],['assessments',['terac.assessment.ai_data']],['customer_evidence',['terac.customer.0']]]){
  if(!Array.isArray(snapshot[table])||snapshot[table].length!==ids.length||!snapshot[table].every((row,index)=>row?.id===ids[index]&&exact(DATA[table].find(item=>item.id===row.id),row)))return false;
 }
 const relationship={name:'Dialogue',relationship:'claimed_customer',description:'Terac’s case study describes recruiting 25 startup founders in under four days. Contract value is undisclosed.',record_ids:['terac.customer.0'],claim_ids:[claimIds[0]]};
 const rows=(window.PROFILE_CONTENT?.entries||[]).find(entry=>entry.company_id==='terac')?.relationships?.filter(row=>row.name==='Dialogue');
 if(rows?.length!==1||!exact(rows[0],relationship)||!Array.isArray(snapshot.profile_relationships)||snapshot.profile_relationships.length!==1||!keys(snapshot.profile_relationships[0],['company_id','relationship'])||snapshot.profile_relationships[0].company_id!=='terac'||!exact(snapshot.profile_relationships[0].relationship,relationship))return false;
 const bindings=[[sourceIds[0]],[sourceIds[2],sourceIds[0]],[sourceIds[0],sourceIds[1]],[sourceIds[0],sourceIds[3]]];
 if(!claimIds.every((id,index)=>{const cl=claims[id];return cl?.company_id==='terac'&&cl.status==='supported'&&cl.confidence==='B'&&cl.segment_scope==='ai_data'&&cl.observed_on==='2026-10-12'&&cl.as_of===(index===0?'2026-05-31':'2026-10-12')&&JSON.stringify(cl.source_ids)===JSON.stringify(bindings[index]);}))return false;
 const assessment=snapshot.assessments[0],customer=snapshot.customer_evidence[0];
 if(assessment.company_id!=='terac'||assessment.segment_scope!=='ai_data'||assessment.as_of!=='2026-10-12'||assessment.rubric_version!=='1.0.0'||assessment.material_conflict!==false||!keys(assessment.gates,['P','C','R','O']))return false;
 if(!Object.entries({P:'2',C:'2',R:'1',O:'1'}).every(([key,level])=>{const gate=assessment.gates[key],id='terac.claim.assessment-evidence-'+key.toLowerCase();return gate.level===level&&JSON.stringify(gate.claim_ids)===JSON.stringify([id])&&(key==='O'||gate.rationale===claims[id].statement);}))return false;
 if(customer.company_id!=='terac'||customer.claim_id!==claimIds[0]||customer.segment_scope!=='ai_data'||customer.relationship!=='claimed_customer'||customer.disclosure!=='company_named'||customer.paid_status!=='unknown')return false;
 const expected=[[sourceIds[0],claimIds[0],'https://terac.com/customers/dialogue-startup-founders','2026-05-31','market_research_engagement'],[sourceIds[1],claimIds[2],'https://terac.com/about',null,'separate_annotation_testimony'],[sourceIds[2],claimIds[1],'https://terac.com/blog/terac-x-berkeley-ai-hackathon','2026-06-18','dated_ai_workflow'],[sourceIds[3],claimIds[3],'https://terac.com/blog/zero-human-company-hackathon','2026-08-12','expert_payout_forecast']];
 return Array.isArray(update.sources)&&update.sources.length===4&&update.sources.every((ref,index)=>{
  const [sid,cid,url,published,role]=expected[index],source=sources[sid];
  return exact(ref,{source_id:sid,claim_id:cid,publication_date:published,publication_date_basis:published?'retained_page_text':'not_established',role,access_status:'retained_readable_page'})&&source.company_id==='terac'&&source.source_type==='company'&&source.retrieval_status==='checked'&&source.url===url&&(source.published_on||null)===published;
 });
}
function financialBasisContextValid(update){
 const metricId='mercor.metric.oct14-major-financial-2',claimId='mercor.claim.oct14-major-financial-2',snapshot=update.historical_snapshot;
 const fields=['id','kind','company_id','reviewed_on','checked_at','review_basis','target','display_basis','display_attribution','context','sources','historical_snapshot'];
 if(Object.keys(update).length!==fields.length||!fields.every(key=>Object.hasOwn(update,key))||update.company_id!=='mercor'||update.target?.metric_id!==metricId||update.target?.claim_id!==claimId||Object.keys(update.target).length!==2)return false;
 if(update.checked_at!==null||update.review_basis!=='retained_public_evidence'||!/^\d{4}-\d{2}-\d{2}$/.test(update.reviewed_on)||!Number.isFinite(Date.parse(update.reviewed_on))||new Date(update.reviewed_on).toISOString().slice(0,10)!==update.reviewed_on||update.reviewed_on>new Date().toISOString().slice(0,10))return false;
 if(typeof update.id!=='string'||!update.id.trim()||typeof update.context!=='string'||!update.context.trim()||/[<>\x00-\x1f]/.test(update.id+update.context))return false;
 if(update.display_basis!=='gross (Sacra estimate)'||update.display_attribution!=='Felicis reports the pace; Sacra estimates the gross basis.')return false;
 if(!snapshot||Object.keys(snapshot).length!==4||snapshot.dataset_version!==DATA.dataset_version||!Array.isArray(snapshot.metrics)||snapshot.metrics.length!==1||!Array.isArray(snapshot.claims)||snapshot.claims.length!==2||!Array.isArray(snapshot.sources)||snapshot.sources.length!==2)return false;
 for(const table of ['metrics','claims','sources'])if(!snapshot[table].every(row=>{const actual=DATA[table].find(item=>item.id===row?.id);return actual&&Object.keys(actual).length===Object.keys(row).length&&evidenceContextSnapshotMatches(actual,row);}))return false;
 const metric=snapshot.metrics[0],claim=claims[claimId];
 if(metric.id!==metricId||metric.company_id!=='mercor'||metric.claim_id!==claimId||metric.kind!=='annualized_revenue_run_rate'||metric.value!==2000000000||metric.currency!=='USD'||metric.unit!=='currency'||metric.qualifier!=='exact'||metric.as_of!=='2026-06'||metric.segment_scope!=='company'||metric.gross_vs_net!=='gross'||metric.reported_vs_estimated!=='reported'||metric.observation_status!=='reported')return false;
 if(!claim||claim.as_of!=='2026-06'||claim.segment_scope!=='company'||JSON.stringify(claim.source_ids)!=='["mercor.source.oct14-88dab2271689"]')return false;
 const expected=[['mercor.source.oct14-88dab2271689',claimId,'investor','https://www.felicis.com/blog/mercor-profile-organizing-human-intelligence-to-power-the-ai-economy','2026-07-21','retained_page_text','bound_investor_run_rate'],['mercor.source.audit-m6','mercor.claim.major-growth_metrics-0','independent_reporting','https://sacra.com/c/mercor/',null,'not_established','secondary_gross_basis_estimate']];
 return Array.isArray(update.sources)&&update.sources.length===2&&update.sources.every((ref,index)=>{
  if(!ref||Object.keys(ref).length!==6)return false;
  const [sourceId,supportId,type,url,published,dateBasis,role]=expected[index],source=sources[sourceId],support=claims[supportId];
  return source?.source_type===type&&source.url===url&&source.company_id==='mercor'&&support?.company_id==='mercor'&&support.status==='supported'&&support.source_ids.includes(sourceId)&&snapshot.sources.some(row=>row.id===sourceId)&&snapshot.claims.some(row=>row.id===supportId)&&ref.source_id===sourceId&&ref.claim_id===supportId&&ref.role===role&&ref.publication_date===published&&ref.publication_date_basis===dateBasis&&ref.access_status==='retained_readable_page'&&(!published||published<=update.reviewed_on)&&(!source.published_on||source.published_on===published);
 });
}
function historicalOfferContextValid(update){
 const keys=(value,expected)=>Boolean(value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===expected.length&&expected.every(key=>Object.hasOwn(value,key)));
 const exact=(actual,expected)=>keys(actual,Object.keys(expected))&&evidenceContextSnapshotMatches(actual,expected);
 const fields=['id','kind','company_id','reviewed_on','checked_at','review_basis','target','affected_claim_ids','display_label','display_period','context','sources','retained_read','historical_snapshot'];
 if(!keys(update,fields)||update.id!=='ooak-data-partner-offer-context-2026-10-17'||update.kind!=='historical-offer-source-context'||update.company_id!=='ooak')return false;
 if(update.reviewed_on!=='2026-10-17'||update.reviewed_on>new Date().toISOString().slice(0,10)||update.checked_at!==null||update.review_basis!=='retained_public_evidence')return false;
 const metricId='ooak.metric.oct14-4-data-partner-payout-cap',claimIds=['ooak.claim.oct14-metric-4-data-partner-payout-cap','ooak.claim.products-1'],sourceIds=['ooak.source.oct14-5bc8f134e0b5','ooak.source.ooak-5'],productId='ooak.product.1';
 if(!exact(update.target,{metric_id:metricId,claim_id:claimIds[0],product_id:productId})||JSON.stringify(update.affected_claim_ids)!==JSON.stringify(claimIds))return false;
 if(update.display_label!=='Original data-partner offer cap'||update.display_period!=='Original snapshot recorded 14 Oct 2026 · Source date not stated'||typeof update.context!=='string'||!update.context.trim()||/[<>\x00-\x1f]/.test(update.context))return false;
 if(update.context!=='Original research records from 12 and 14 October 2026 list up to $300K for company-data licensing. In a retained read from 16 October, the official partner page advertises up to $1M for the same offer. These are marketing ceilings for payment to the company, subject to a data audit; they are not individual pay rates or guaranteed payments. The change date is not established.')return false;
 const retained={started_at:'2026-10-16 23:56:42 UTC',completed_at:'2026-10-16 23:56:43 UTC',raw_evidence_file:'output/reliability-20261016-2247/link-reader-1/batch-166-166-raw.json',sha256:'1cb6464c6c50bef5794381345afefd2436cf5b87a501b9c6339ad86186b3da77',source_publication_date:null,change_date:null};
 if(!exact(update.retained_read,retained))return false;
 const snapshot=update.historical_snapshot;
 if(!keys(snapshot,['dataset_version','metrics','claims','sources','products'])||snapshot.dataset_version!=='2.5.0'||snapshot.dataset_version!==DATA.dataset_version)return false;
 for(const [table,ids]of [['metrics',[metricId]],['claims',claimIds],['sources',sourceIds],['products',[productId]]])if(!Array.isArray(snapshot[table])||snapshot[table].length!==ids.length||!snapshot[table].every((row,index)=>row?.id===ids[index]&&exact(DATA[table].find(item=>item.id===row.id),row)))return false;
 const metric=snapshot.metrics[0],expectedMetric={company_id:'ooak',claim_id:claimIds[0],kind:'other',value:300000,qualifier:'at_most',currency:'USD',unit:'currency',as_of:'undated',segment_scope:'company',gross_vs_net:'unspecified',reported_vs_estimated:'reported',observation_status:'reported',label:'Data partner payout cap'};
 if(!evidenceContextSnapshotMatches(metric,expectedMetric))return false;
 if(!claimIds.every((id,index)=>{const cl=claims[id],src=sources[sourceIds[index]];return cl.company_id==='ooak'&&cl.status==='supported'&&cl.confidence==='B'&&cl.as_of===(index===0?'undated':'2026-10-12')&&cl.observed_on===(index===0?'2026-10-14':'2026-10-12')&&cl.segment_scope===(index===0?'company':'ai_data')&&JSON.stringify(cl.source_ids)===JSON.stringify([sourceIds[index]])&&src.company_id==='ooak'&&src.source_type==='company'&&src.retrieval_status==='checked'&&src.url==='https://ooakdata.com/partner'&&!src.published_on&&src.accessed_on===cl.observed_on;}))return false;
 const product=snapshot.products[0];if(product.company_id!=='ooak'||product.claim_id!==claimIds[1]||product.segment_scope!=='ai_data'||product.work_performed!==claims[claimIds[1]].statement)return false;
 return Array.isArray(update.sources)&&update.sources.length===1&&exact(update.sources[0],{source_id:sourceIds[0],claim_id:claimIds[0],publication_date:null,publication_date_basis:'not_established',role:'retained_issuer_offer',access_status:'retained_readable_page'});
}
function evidenceContextCorrections(){
 const document=window.SOURCE_UPDATES,section=document?.evidence_context;
 if(document?.baseline_dataset_version!==DATA.dataset_version||section?.version!=='1.0.0'||!Array.isArray(section.corrections))return [];
 return section.corrections.filter(update=>{
  if(update?.kind==='historical-offer-source-context')return section.corrections.filter(row=>row?.id===update.id||row?.kind===update.kind).length===1&&!(document.updates||[]).some(row=>row.id===update.id)&&historicalOfferContextValid(update);
  if(update?.kind==='relationship-assessment-scope-context')return section.corrections.filter(row=>row?.id===update.id||row?.kind===update.kind).length===1&&!(document.updates||[]).some(row=>row.id===update.id)&&relationshipAssessmentContextValid(update);
  if(!['metric_reporting_context','claim_source_supplement','financial-basis-source-supplement'].includes(update?.kind))return false;
  if(update.kind==='financial-basis-source-supplement'&&!financialBasisContextValid(update))return false;
  const snapshot=update?.historical_snapshot;
  if(snapshot?.dataset_version!==DATA.dataset_version||!update.target||!Array.isArray(update.sources))return false;
  if(!['metrics','claims','sources'].every(table=>Array.isArray(snapshot[table])))return false;
  if(!snapshot.claims.length||!snapshot.sources.length)return false;
  if(!snapshot.claims.every(row=>row&&evidenceContextSnapshotMatches(claims[row.id],row)))return false;
  if(!snapshot.sources.every(row=>row&&evidenceContextSnapshotMatches(sources[row.id],row)))return false;
  if(!snapshot.metrics.every(row=>row&&evidenceContextSnapshotMatches(DATA.metrics.find(metric=>metric.id===row.id),row)))return false;
  return snapshot.claims.some(row=>row.id===update.target.claim_id&&row.company_id===update.company_id)&&update.sources.every(ref=>ref&&snapshot.sources.some(row=>row.id===ref.source_id));
 });
}
function evidenceContextForMetric(metric){
 return evidenceContextCorrections().find(update=>update.kind==='metric_reporting_context'&&update.company_id===metric.company_id&&update.target.metric_id===metric.id&&update.target.claim_id===metric.claim_id&&evidenceContextSnapshotMatches(metric,update.historical_snapshot.metrics[0]));
}
function financialBasisContextForMetric(metric){
 return evidenceContextCorrections().find(update=>update.kind==='financial-basis-source-supplement'&&update.target.metric_id===metric.id&&update.target.claim_id===metric.claim_id&&evidenceContextSnapshotMatches(metric,update.historical_snapshot.metrics[0]));
}
function metricCurrentBasis(metric,fallback){return financialBasisContextForMetric(metric)?.display_basis||fallback;}
function metricCurrentAttribution(metric,fallback){return financialBasisContextForMetric(metric)?.display_attribution||fallback;}
function metricCurrentBasisDescription(metric,fallback){return financialBasisContextForMetric(metric)?'Gross is customer spend before contractor payouts, per Sacra’s estimate.':fallback;}
function historicalOfferContextForMetric(metric){return evidenceContextCorrections().find(update=>update.kind==='historical-offer-source-context'&&update.target.metric_id===metric?.id&&update.target.claim_id===metric.claim_id&&evidenceContextSnapshotMatches(metric,update.historical_snapshot.metrics[0]));}
function metricPresentationLabel(metric,fallback){return historicalOfferContextForMetric(metric)?.display_label||fallback;}
function metricEvidenceTopic(metric,fallback){return historicalOfferContextForMetric(metric)?'Original data-partner offer cap; snapshot recorded 14 October 2026':financialBasisContextForMetric(metric)?fallback+'; gross basis from Sacra estimate':fallback;}
function evidenceContextForClaim(claim){
 return evidenceContextCorrections().filter(update=>update.company_id===claim.company_id&&(update.target.claim_id===claim.id||['relationship-assessment-scope-context','historical-offer-source-context'].includes(update.kind)&&update.affected_claim_ids.includes(claim.id)));
}
function relationshipAssessmentContextForClaim(claim){
 return claim&&evidenceContextForClaim(claim).find(update=>update.kind==='relationship-assessment-scope-context'&&evidenceContextSnapshotMatches(claim,update.historical_snapshot.claims.find(row=>row.id===claim.id)));
}
function evidenceContextScopeLabel(claim,fallback){const update=relationshipAssessmentContextForClaim(claim);return update&&update.target.claim_id===claim?.id?update.display_scope:fallback;}
function evidenceContextClaimDescription(claim){const offer=historicalOfferContextForClaim(claim);if(offer)return offer.context;const update=relationshipAssessmentContextForClaim(claim);return update?(claim.id===update.target.claim_id?update.context:update.criterion_context[claim.id.slice(-1).toUpperCase()]||''):'';}
function historicalOfferContextForClaim(claim){return claim&&evidenceContextForClaim(claim).find(update=>update.kind==='historical-offer-source-context');}
function evidenceContextStatementHeading(claim){return historicalOfferContextForClaim(claim)?'Original dataset statement · recorded '+profileDate(claim.observed_on):relationshipAssessmentContextForClaim(claim)?'Original dataset statement':'';}
function originalProductContextHTML(product){const update=evidenceContextCorrections().find(row=>row.kind==='historical-offer-source-context'&&row.target.product_id===product?.id&&evidenceContextSnapshotMatches(product,row.historical_snapshot.products[0]));return update?evidenceContextUpdateHTML(update)+evidenceContextStatementHeadingHTML(claims[product.claim_id]):'';}
function evidenceContextStatementHeadingHTML(claim){const heading=evidenceContextStatementHeading(claim);return heading?`<p class="sub"><strong>${esc(heading)}</strong></p>`:'';}
function evidenceContextOriginalScope(claim,fallback){return evidenceContextScopeLabel(claim,fallback)!==fallback?'Original dataset scope: '+fallback:fallback;}
function evidenceContextScopeHTML(claim,fallback){const current=evidenceContextScopeLabel(claim,fallback);return current!==fallback?`<div><strong>Reviewed engagement scope</strong>${esc(current)}</div><div><strong>Original dataset scope</strong>${esc(fallback)}</div>`:`<div><strong>Entity scope</strong>${esc(fallback)}</div>`;}
function relationshipAssessmentContextForAssessment(assessment){return evidenceContextCorrections().find(update=>update.kind==='relationship-assessment-scope-context'&&update.target.assessment_id===assessment?.id&&evidenceContextSnapshotMatches(assessment,update.historical_snapshot.assessments[0]));}
function evidenceContextAssessmentHTML(assessment){const update=relationshipAssessmentContextForAssessment(assessment);return update?evidenceContextUpdateHTML(update)+`<p class="sub"><strong>Original assessment rationale</strong></p>`:'';}
function evidenceContextCriterionHTML(assessment,key){const update=relationshipAssessmentContextForAssessment(assessment);return update&&Object.hasOwn(update.criterion_context,key)?`<p class="sub">${esc(update.criterion_context[key])}</p><p class="sub"><strong>Original criterion rationale</strong></p>`:'';}
function profileRelationshipScopeContext(id,row){const update=evidenceContextCorrections().find(update=>update.kind==='relationship-assessment-scope-context'&&update.company_id===id);return update&&evidenceContextSnapshotMatches(row,update.historical_snapshot.profile_relationships[0].relationship)?update.relationship_context:'';}
function metricCurrentPeriod(metric,fallback=''){
 return evidenceContextForMetric(metric)?.display_period||fallback;
}
function evidenceContextClaimPeriod(claim,fallback){
 if(historicalOfferContextForClaim(claim))return 'Original dataset date field: '+fallback;
 return evidenceContextForClaim(claim).find(update=>update.kind==='metric_reporting_context')?.display_period||fallback;
}
function evidenceContextDateHeading(claim){
 if(historicalOfferContextForClaim(claim))return 'Original dataset date field';
 return evidenceContextForClaim(claim).some(update=>update.kind==='metric_reporting_context')?'Original dataset reporting date':'Evidence / reporting date';
}
function evidenceContextArchiveDate(claim,fallback){
 if(historicalOfferContextForClaim(claim))return 'Original dataset date field: '+fallback;
 return evidenceContextForClaim(claim).some(update=>update.kind==='metric_reporting_context')?'Original dataset reporting date: '+fallback:fallback;
}
function metricContextMetaPeriod(metric,fallback){
 const offer=historicalOfferContextForMetric(metric);if(offer)return offer.display_period;
 const update=evidenceContextForMetric(metric);
 return update?update.display_period+' · Original dataset reporting date: '+fallback:fallback;
}
function evidenceContextUpdateHTML(update,claimId){
 const scope=update.kind==='relationship-assessment-scope-context',label=scope?'Engagement and assessment scope clarification':update.kind==='historical-offer-source-context'?'Company-data licensing offer · source context reviewed':update.kind==='metric_reporting_context'?'Reporting-date clarification':update.kind==='financial-basis-source-supplement'?'Gross-basis source clarification':'Source-link supplement';
 const context=scope?(claimId?evidenceContextClaimDescription(claims[claimId]):update.assessment_context):update.context;
 const links=update.sources.map(ref=>{
  const source=sources[ref.source_id],role={bound_gross_observation:'Database report',separate_investor_corroboration:'Separate investor corroboration',direct_financial_support:'CEO post',bound_investor_run_rate:'Felicis · investor-published company statement',secondary_gross_basis_estimate:'Sacra · separate secondary gross estimate',market_research_engagement:'Dialogue market-research case',separate_annotation_testimony:'Spade annotation testimony',dated_ai_workflow:'Dated AI workflow',expert_payout_forecast:'Expert-payout forecast',retained_issuer_offer:'Ooak partner page · retained read 16 Oct 2026 · publication date not stated'}[ref.role];
  return `<li>${external(source.url,role)}${ref.publication_date?' · Published '+esc(profileDate(ref.publication_date)):''}${ref.role==='direct_financial_support'?' · '+claimButton(ref.claim_id,'Retained financial evidence'):''}</li>`;
 }).join('');
 return `<aside class="source-update-note" data-evidence-context="${attr(update.id)}"><p><strong>${esc(label)} · ${esc(profileDate(update.reviewed_on))}</strong></p><p>${esc(context)}</p>${update.access_note?`<p class="sub">${esc(update.access_note)}</p>`:''}<ul>${links}</ul><p class="sub">${scope?`Based on retained research. This clarification is not a new source check. Original dataset ${esc(DATA.dataset_version)} statements, assessment values and source lists are retained.`:`Based on retained research. This correction is not a new source check. The original dataset ${esc(DATA.dataset_version)} record and sources are retained.`}</p><p><a href="source-updates.json" download>Source updates and original records · JSON</a></p></aside>`;
}
function evidenceContextClaimHTML(id){
 const claim=claims[id];return claim?evidenceContextForClaim(claim).map(update=>evidenceContextUpdateHTML(update,id)).join(''):'';
}
function evidenceContextArchiveHTML(id){
 return evidenceContextCorrections().filter(update=>update.company_id===id).map(update=>evidenceContextUpdateHTML(update)).join('');
}
