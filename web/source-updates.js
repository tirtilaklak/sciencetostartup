/* Later official-source corrections. The original research datasets stay intact. */
function sourceUpdatesFor(id){return detailViewRenderer("sourceUpdatesFor",this,arguments);}
function sourceUpdateUnknownText(id,original){return detailViewRenderer("sourceUpdateUnknownText",this,arguments);}
function applyProductSourceUpdates(id,rows){return detailViewRenderer("applyProductSourceUpdates",this,arguments);}
function sourceUpdateReferenceHTML(update,label='Company source'){return detailViewRenderer("sourceUpdateReferenceHTML",this,arguments);}
function productSourceHTML(product,label='Source',topic=''){return detailViewRenderer("productSourceHTML",this,arguments);}
function productSourceContextHTML(product){return detailViewRenderer("productSourceContextHTML",this,arguments);}
function sourceUpdatesArchiveHTML(id){return detailViewRenderer("sourceUpdatesArchiveHTML",this,arguments);}
function sourceUpdateClaimHTML(id){return detailViewRenderer("sourceUpdateClaimHTML",this,arguments);}

// Context corrections never replace canonical metrics, claims or source lists.
function evidenceContextSnapshotMatches(actual,expected){return detailViewRenderer("evidenceContextSnapshotMatches",this,arguments);}
function relationshipAssessmentContextValid(update){return detailViewRenderer("relationshipAssessmentContextValid",this,arguments);}
function financialBasisContextValid(update){return detailViewRenderer("financialBasisContextValid",this,arguments);}
function historicalOfferContextValid(update){return detailViewRenderer("historicalOfferContextValid",this,arguments);}
let evidenceContextCache=null,evidenceContextCacheSource;
function evidenceContextCorrections(){return detailViewRenderer("evidenceContextCorrections",this,arguments);}
function evidenceContextCorrectionsCompute(){return detailViewRenderer("evidenceContextCorrectionsCompute",this,arguments);}
function evidenceContextForMetric(metric){return detailViewRenderer("evidenceContextForMetric",this,arguments);}
function financialBasisContextForMetric(metric){return detailViewRenderer("financialBasisContextForMetric",this,arguments);}
function metricCurrentBasis(metric,fallback){return detailViewRenderer("metricCurrentBasis",this,arguments);}
function metricCurrentAttribution(metric,fallback){return detailViewRenderer("metricCurrentAttribution",this,arguments);}
function metricCurrentBasisDescription(metric,fallback){return detailViewRenderer("metricCurrentBasisDescription",this,arguments);}
function historicalOfferContextForMetric(metric){return detailViewRenderer("historicalOfferContextForMetric",this,arguments);}
function metricPresentationLabel(metric,fallback){return detailViewRenderer("metricPresentationLabel",this,arguments);}
function metricEvidenceTopic(metric,fallback){return detailViewRenderer("metricEvidenceTopic",this,arguments);}
function evidenceContextForClaim(claim){return detailViewRenderer("evidenceContextForClaim",this,arguments);}
function relationshipAssessmentContextForClaim(claim){return detailViewRenderer("relationshipAssessmentContextForClaim",this,arguments);}
function evidenceContextScopeLabel(claim,fallback){return detailViewRenderer("evidenceContextScopeLabel",this,arguments);}
function evidenceContextClaimDescription(claim){return detailViewRenderer("evidenceContextClaimDescription",this,arguments);}
function historicalOfferContextForClaim(claim){return detailViewRenderer("historicalOfferContextForClaim",this,arguments);}
function evidenceContextStatementHeading(claim){return detailViewRenderer("evidenceContextStatementHeading",this,arguments);}
function originalProductContextHTML(product){return detailViewRenderer("originalProductContextHTML",this,arguments);}
function evidenceContextStatementHeadingHTML(claim){return detailViewRenderer("evidenceContextStatementHeadingHTML",this,arguments);}
function evidenceContextOriginalScope(claim,fallback){return detailViewRenderer("evidenceContextOriginalScope",this,arguments);}
function evidenceContextScopeHTML(claim,fallback){return detailViewRenderer("evidenceContextScopeHTML",this,arguments);}
function relationshipAssessmentContextForAssessment(assessment){return detailViewRenderer("relationshipAssessmentContextForAssessment",this,arguments);}
function evidenceContextAssessmentHTML(assessment){return detailViewRenderer("evidenceContextAssessmentHTML",this,arguments);}
function evidenceContextCriterionHTML(assessment,key){return detailViewRenderer("evidenceContextCriterionHTML",this,arguments);}
function profileRelationshipScopeContext(id,row){return detailViewRenderer("profileRelationshipScopeContext",this,arguments);}
function metricCurrentPeriod(metric,fallback=''){return detailViewRenderer("metricCurrentPeriod",this,arguments);}
function evidenceContextClaimPeriod(claim,fallback){return detailViewRenderer("evidenceContextClaimPeriod",this,arguments);}
function evidenceContextDateHeading(claim){return detailViewRenderer("evidenceContextDateHeading",this,arguments);}
function evidenceContextArchiveDate(claim,fallback){return detailViewRenderer("evidenceContextArchiveDate",this,arguments);}
function metricContextMetaPeriod(metric,fallback){return detailViewRenderer("metricContextMetaPeriod",this,arguments);}
function evidenceContextUpdateHTML(update,claimId){return detailViewRenderer("evidenceContextUpdateHTML",this,arguments);}
function evidenceContextClaimHTML(id){return detailViewRenderer("evidenceContextClaimHTML",this,arguments);}
function evidenceContextArchiveHTML(id){return detailViewRenderer("evidenceContextArchiveHTML",this,arguments);}
