// Background service worker for TalentVault Extension
chrome.sidePanel
  ?.setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.log('Sidepanel behavior fallback:', error));

chrome.runtime.onInstalled.addListener(() => {
  console.log('TalentVault Candidate Importer extension installed.');
});
