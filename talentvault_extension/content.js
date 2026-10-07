// Enhanced Content Script for TalentVault Candidate Importer Extension
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "extract_candidate_data") {
    // 1. Expand inline "...see more" and "Show all" buttons if present
    try {
      const seeMoreBtns = document.querySelectorAll('.inline-show-more-text__button, .pv-about-section__see-more, .lt-line-clamp__more, button.pv-profile-section__see-more-inline');
      seeMoreBtns.forEach(btn => {
        try { btn.click(); } catch(e){}
      });
    } catch (e) {}

    // 2. Perform a micro-scroll check to trigger dynamic lazy-rendered DOM sections
    try {
      window.scrollBy(0, 400);
      window.scrollBy(0, -400);
    } catch (e) {}

    setTimeout(() => {
      try {
        const data = extractPageData();
        console.log(`[TalentVault Extraction Log] Candidate Name: "${data.name}", Headline: "${data.headline}", Current Company: "${data.current_company}", Location: "${data.location}"`);
        console.log(`[TalentVault Extraction Log] Found ${data.experience.length} Experience entries, ${data.education.length} Education entries, ${data.skills.length} Skills.`);
        sendResponse({ status: "success", data: data, logs: { experienceCount: data.experience.length, educationCount: data.education.length, skillsCount: data.skills.length } });
      } catch (err) {
        console.error("TalentVault extraction error:", err);
        sendResponse({ status: "error", error: err.message });
      }
    }, 200);
    return true;
  }
  return true;
});

function extractPageData() {
  const hostname = window.location.hostname.toLowerCase();
  let source = "web_import";
  if (hostname.includes("linkedin.com")) {
    source = "linkedin";
  } else if (hostname.includes("naukri.com")) {
    source = "naukri";
  }

  let base = {
    name: "",
    email: "",
    phone: "",
    headline: "",
    current_company: "",
    location: "",
    summary: "",
    total_experience: null,
    current_salary: null,
    expected_salary: null,
    notice_period: null,
    experience: [],
    education: [],
    skills: [],
    profile_url: window.location.href.split("?")[0].split("#")[0],
    source: source
  };

  if (source === "linkedin") {
    base = extractLinkedInData(base);
  } else if (source === "naukri") {
    base = extractNaukriData(base);
  } else {
    base = extractGenericData(base);
  }

  // Extract CTC & Notice Period ONLY if genuinely present in profile text (never invent values)
  const fullText = (base.summary + " " + base.headline + " " + (document.body ? document.body.innerText : "")).substring(0, 5000);

  // Extract email & phone number when present in the profile text
  base.email = extractEmailFromText(fullText);
  base.phone = extractPhoneFromText(fullText);

  const npMatch = fullText.match(/(?:notice\s*period|np|joining\s*time)[:\s]*(\d+)\s*(days?|months?)/i);
  const immMatch = fullText.match(/(immediate\s*joiner|open\s*to\s*join\s*immediately)/i);
  if (immMatch) {
    base.notice_period = 0;
  } else if (npMatch) {
    let days = parseInt(npMatch[1], 10);
    if (npMatch[2].toLowerCase().startsWith("month")) {
      days = days * 30;
    }
    base.notice_period = days;
  }

  const ctcMatch = fullText.match(/(?:current\s*ctc|ctc|current\s*salary)[:\s]*([\d\.]+)\s*(lpa|lakhs?|lac)/i);
  if (ctcMatch) {
    base.current_salary = parseFloat(ctcMatch[1]);
  }

  const expCtcMatch = fullText.match(/(?:expected\s*ctc|expected\s*salary)[:\s]*([\d\.]+)\s*(lpa|lakhs?|lac)/i);
  if (expCtcMatch) {
    base.expected_salary = parseFloat(expCtcMatch[1]);
  }

  // Calculate total experience if not explicitly found
  if (!base.total_experience && base.experience.length > 0) {
    let calculatedExp = calculateTotalExperienceYears(base.experience);
    if (calculatedExp > 0) {
      base.total_experience = calculatedExp;
    }
  }

  // Fallback cleanup if name missing
  if (!base.name) {
    const pageTitle = document.title || "";
    if (pageTitle.includes("|")) {
      base.name = pageTitle.split("|")[0].trim();
    } else if (pageTitle.includes("-")) {
      base.name = pageTitle.split("-")[0].trim();
    } else {
      base.name = pageTitle.trim();
    }
    if (base.name.toLowerCase().includes("linkedin") || base.name.toLowerCase().includes("naukri")) {
      base.name = "";
    }
  }

  return base;
}

function calculateTotalExperienceYears(experiences) {
  let totalMonths = 0;
  const yearRegex = /\b(19\d\d|20\d\d)\b/g;

  experiences.forEach(exp => {
    const durStr = exp.duration || exp.dates || "";
    if (!durStr) return;

    // e.g. "4 yrs 10 mos" or "Jan 2018 - Dec 2022"
    const yrMatch = durStr.match(/(\d+)\s*yrs?/i);
    const moMatch = durStr.match(/(\d+)\s*mos?/i);
    if (yrMatch || moMatch) {
      const yrs = yrMatch ? parseInt(yrMatch[1], 10) : 0;
      const mos = moMatch ? parseInt(moMatch[1], 10) : 0;
      totalMonths += (yrs * 12 + mos);
      return;
    }

    const years = durStr.match(yearRegex);
    if (years && years.length >= 1) {
      const startYr = parseInt(years[0], 10);
      let endYr = new Date().getFullYear();
      if (years.length >= 2 && !durStr.toLowerCase().includes("present")) {
        endYr = parseInt(years[1], 10);
      }
      const diff = (endYr - startYr) * 12;
      if (diff > 0) totalMonths += diff;
    }
  });

  return totalMonths > 0 ? parseFloat((totalMonths / 12.0).toFixed(1)) : null;
}

// Helper to extract clean visible text without duplicated accessibility fragments
function getCleanText(node) {
  if (!node) return "";
  const clone = node.cloneNode(true);
  
  const noiseEls = clone.querySelectorAll('script, style, .visually-hidden:not(:only-child), .sr-only, .inline-show-more-text__button');
  noiseEls.forEach(el => el.remove());

  const ariaSpans = clone.querySelectorAll('span[aria-hidden="true"]');
  if (ariaSpans.length > 0) {
    const textArr = Array.from(ariaSpans)
      .map(s => (s.innerText || s.textContent || "").trim())
      .filter(t => t.length > 0);
    if (textArr.length > 0) {
      return sanitizeString(textArr.join(" "));
    }
  }

  const rawText = clone.innerText || clone.textContent || "";
  return sanitizeString(rawText);
}

function sanitizeString(str) {
  if (!str) return "";
  let clean = str.replace(/[\r\n\t]+/g, " ").replace(/\s+/g, " ").trim();
  const parts = clean.split(" • ");
  if (parts.length === 2 && parts[0] === parts[1]) {
    clean = parts[0];
  }
  return clean;
}

function cleanCompanyName(companyStr) {
  if (!companyStr) return "";
  let cleaned = companyStr.split("·")[0].split("•")[0].split(" Full-time")[0].split(" Part-time")[0].trim();
  return cleaned;
}

function normalizePhoneNumber(str) {
  if (!str) return "";
  let clean = String(str).replace(/[\s\-().]/g, "");
  clean = clean.replace(/[^\d+]/g, "");
  return clean;
}

function extractEmailFromText(text) {
  if (!text) return "";
  const match = text.match(/[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/);
  return match ? match[0] : "";
}

function extractPhoneFromText(text) {
  if (!text) return "";
  const labelMatch = text.match(/(?:phone|mobile|contact|tel|call|whatsapp)[\s:.#]*([+\d][\d\s\-().]{6,20}\d)/i);
  if (labelMatch) {
    return normalizePhoneNumber(labelMatch[1]);
  }
  const fallback = text.match(/(?:\+?\d{1,3}[\s\-]?)?(?:\(\d{2,4}\)[\s\-]?)?\d{3,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}/);
  if (fallback) {
    return normalizePhoneNumber(fallback[0]);
  }
  return "";
}

// Robust section finder by ID or Heading Keywords
function findSection(idAnchor, headingKeywords) {
  if (idAnchor) {
    const el = document.getElementById(idAnchor);
    if (el) {
      const sec = el.closest('section') || el.closest('div.pv-profile-section') || el.parentElement;
      if (sec) return sec;
    }
  }

  const containers = document.querySelectorAll('section, div.pv-profile-section, div.artdeco-card, div.card, div.widget, div.section');
  for (const container of containers) {
    const header = container.querySelector('h2, h3, .pvs-header__title, .card-title, .section-title, span.text-heading-large');
    if (header) {
      const hText = (header.innerText || header.textContent || "").toLowerCase();
      if (headingKeywords.some(kw => hText.includes(kw))) {
        return container;
      }
    }
  }
  return null;
}

function extractLinkedInData(base) {
  // 1. Name
  const nameSelectors = [
    'h1.text-heading-xlarge',
    '.pv-text-details__left-panel h1',
    '[data-anonymize="person-name"]',
    '.top-card-layout__title',
    'h1'
  ];
  for (const sel of nameSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const txt = getCleanText(el);
      if (txt && !txt.toLowerCase().includes("linkedin") && !txt.toLowerCase().includes("sign in")) {
        base.name = txt;
        break;
      }
    }
  }

  // 2. Headline
  const headlineSelectors = [
    '.text-body-medium.break-words',
    '.pv-text-details__left-panel .text-body-medium',
    '[data-generated-suggestion-target]',
    '[data-anonymize="headline"]',
    '.top-card-layout__headline',
    'div.text-body-medium'
  ];
  for (const sel of headlineSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const txt = getCleanText(el);
      if (txt && txt !== base.name) {
        base.headline = txt;
        break;
      }
    }
  }

  // 3. Location
  const locationSelectors = [
    'span.text-body-small.inline.t-black--light.break-words',
    '.pv-text-details__left-panel span.text-body-small',
    '.pb2 .text-body-small',
    '[data-anonymize="location"]',
    '.top-card-layout__first-subtext'
  ];
  for (const sel of locationSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const txt = getCleanText(el);
      if (txt && !txt.toLowerCase().includes("contact info") && !txt.toLowerCase().includes("connections")) {
        base.location = txt;
        break;
      }
    }
  }

  // 4. Current Company (Top Card Right Panel or Header)
  const compSelectors = [
    'ul.pv-text-details__right-panel li button span',
    'ul.pv-text-details__right-panel li',
    'div.pv-text-details__right-panel'
  ];
  for (const sel of compSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const txt = cleanCompanyName(getCleanText(el));
      if (txt && txt.length < 100) {
        base.current_company = txt;
        break;
      }
    }
  }

  // 5. About / Summary
  const aboutSec = findSection('about', ['about', 'summary', 'overview']);
  if (aboutSec) {
    const aboutTextEl = aboutSec.querySelector('.pv-shared-text-with-see-more span[aria-hidden="true"]') ||
                        aboutSec.querySelector('.inline-show-more-text span[aria-hidden="true"]') ||
                        aboutSec.querySelector('.inline-show-more-text') ||
                        aboutSec.querySelector('.pv-about-section');
    if (aboutTextEl) {
      base.summary = getCleanText(aboutTextEl);
    } else {
      const pArr = Array.from(aboutSec.querySelectorAll('p, span')).map(p => getCleanText(p)).filter(t => t.length > 20);
      if (pArr.length > 0) base.summary = pArr[0];
    }
  }

  // 6. Experience (ALL visible entries)
  const expSec = findSection('experience', ['experience', 'work experience', 'employment']);
  if (expSec) {
    const items = expSec.querySelectorAll('ul.pvs-list > li, li.artdeco-list__item, div.pvs-entity');
    items.forEach((item) => {
      const subListItems = item.querySelectorAll('ul.pvs-list > li');
      if (subListItems.length > 0) {
        // Multi-role company
        const topTitle = item.querySelector('.t-bold span[aria-hidden="true"]') || item.querySelector('.t-bold');
        const companyName = cleanCompanyName(getCleanText(topTitle));

        subListItems.forEach((subLi) => {
          const flexLines = subLi.querySelectorAll('.display-flex.flex-column span[aria-hidden="true"], .t-bold span[aria-hidden="true"], .t-14.t-normal span[aria-hidden="true"]');
          let desig = "";
          let dur = "";
          let loc = "";

          if (flexLines.length >= 1) desig = getCleanText(flexLines[0]);
          if (flexLines.length >= 2) dur = getCleanText(flexLines[1]);
          if (flexLines.length >= 3) loc = getCleanText(flexLines[2]);

          const descEl = subLi.querySelector('.inline-show-more-text, .pv-shared-text-with-see-more');
          const desc = getCleanText(descEl);

          if (desig || companyName) {
            base.experience.push({
              company_name: companyName || "Not Specified",
              designation: desig || "Not Specified",
              duration: dur,
              dates: dur,
              location: loc,
              description: desc
            });
          }
        });
      } else {
        // Single role entry
        const flexLines = item.querySelectorAll('.display-flex.flex-column span[aria-hidden="true"], .t-bold span[aria-hidden="true"], .t-14.t-normal span[aria-hidden="true"]');
        let desig = "";
        let comp = "";
        let dur = "";
        let loc = "";

        if (flexLines.length >= 1) desig = getCleanText(flexLines[0]);
        if (flexLines.length >= 2) comp = cleanCompanyName(getCleanText(flexLines[1]));
        if (flexLines.length >= 3) dur = getCleanText(flexLines[2]);
        if (flexLines.length >= 4) loc = getCleanText(flexLines[3]);

        const descEl = item.querySelector('.inline-show-more-text, .pv-shared-text-with-see-more');
        const desc = getCleanText(descEl);

        if (desig || comp) {
          base.experience.push({
            company_name: comp || "Not Specified",
            designation: desig || "Not Specified",
            duration: dur,
            dates: dur,
            location: loc,
            description: desc
          });
        }
      }
    });

    if (!base.current_company && base.experience.length > 0) {
      base.current_company = base.experience[0].company_name;
    }
  }

  // 7. Education (ALL visible entries)
  const eduSec = findSection('education', ['education', 'academic', 'qualification']);
  if (eduSec) {
    const items = eduSec.querySelectorAll('ul.pvs-list > li, li.artdeco-list__item');
    items.forEach((item) => {
      const flexLines = item.querySelectorAll('.display-flex.flex-column span[aria-hidden="true"], .t-bold span[aria-hidden="true"], .t-14.t-normal span[aria-hidden="true"]');
      let inst = "";
      let deg = "";
      let dates = "";
      let field = "";

      if (flexLines.length >= 1) inst = getCleanText(flexLines[0]);
      if (flexLines.length >= 2) {
        const fullDeg = getCleanText(flexLines[1]);
        if (fullDeg.includes(",")) {
          const parts = fullDeg.split(",");
          deg = parts[0].trim();
          field = parts.slice(1).join(",").trim();
        } else {
          deg = fullDeg;
        }
      }
      if (flexLines.length >= 3) dates = getCleanText(flexLines[2]);

      if (inst || deg) {
        base.education.push({
          institution: inst || "Not Specified",
          degree: deg || "Not Specified",
          field_of_study: field || null,
          dates: dates
        });
      }
    });
  }

  // 8. Skills (ALL visible entries)
  const skillsSec = findSection('skills', ['skills', 'competencies', 'endorsement']);
  if (skillsSec) {
    const skillItems = skillsSec.querySelectorAll('ul.pvs-list > li, .hoverable-link-text, .pv-skill-category-entity__name-text');
    skillItems.forEach((item) => {
      const sSpan = item.querySelector('span[aria-hidden="true"]') || item;
      const sName = getCleanText(sSpan);
      if (sName && !sName.toLowerCase().includes("endorse") && !sName.toLowerCase().includes("skill") && sName.length < 60) {
        if (!base.skills.includes(sName)) {
          base.skills.push(sName);
        }
      }
    });
  }

  return base;
}

function extractNaukriData(base) {
  // 1. Name
  const nameSelectors = ['.info .name', '.user-name', '.candidate-name', '.profile-header .name', 'h1'];
  for (const sel of nameSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const txt = getCleanText(el);
      if (txt) { base.name = txt; break; }
    }
  }

  // 2. Headline
  const headlineSelectors = ['.resume-headline-text', '.designation', '.title-container', '.profile-header .desig', '.headline'];
  for (const sel of headlineSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const txt = getCleanText(el);
      if (txt) { base.headline = txt; break; }
    }
  }

  // 3. Location
  const locSelectors = ['.location', '.user-location', '.loc', '.profile-header .location'];
  for (const sel of locSelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const txt = getCleanText(el);
      if (txt) { base.location = txt; break; }
    }
  }

  // 4. Summary
  const summarySelectors = ['.profile-summary-text', '.summary-text', '#resumeHeadline', '.profile-summary'];
  for (const sel of summarySelectors) {
    const el = document.querySelector(sel);
    if (el) {
      const txt = getCleanText(el);
      if (txt) { base.summary = txt; break; }
    }
  }

  // 5. Experience
  const expCards = document.querySelectorAll('.exp-details, .work-experience, .exp-card, .employment-container, .job-profile');
  expCards.forEach((card) => {
    const compEl = card.querySelector('.company-name, .org, .company');
    const desigEl = card.querySelector('.designation, .role, .title');
    const durEl = card.querySelector('.duration, .exp-time, .dates');
    const locEl = card.querySelector('.location, .loc');
    const descEl = card.querySelector('.description, .job-details');

    const comp = getCleanText(compEl);
    const desig = getCleanText(desigEl);
    if (comp || desig) {
      base.experience.push({
        company_name: comp || "Not Specified",
        designation: desig || "Not Specified",
        duration: getCleanText(durEl),
        dates: getCleanText(durEl),
        location: getCleanText(locEl),
        description: getCleanText(descEl)
      });
    }
  });

  if (!base.current_company && base.experience.length > 0) {
    base.current_company = base.experience[0].company_name;
  }

  // 6. Education
  const eduCards = document.querySelectorAll('.education-details, .edu-card, .education-container');
  eduCards.forEach((card) => {
    const instEl = card.querySelector('.institute, .school-name, .college');
    const degEl = card.querySelector('.degree, .qualification');
    const fieldEl = card.querySelector('.specialization, .field');
    const durEl = card.querySelector('.dates, .duration');

    const inst = getCleanText(instEl);
    const deg = getCleanText(degEl);
    if (inst || deg) {
      base.education.push({
        institution: inst || "Not Specified",
        degree: deg || "Not Specified",
        field_of_study: getCleanText(fieldEl),
        dates: getCleanText(durEl)
      });
    }
  });

  // 7. Skills
  const skillEls = document.querySelectorAll('.key-skill .chip, .skills-container .skill-name, .key-skills span, .skill-tag, .skills-wrapper span');
  skillEls.forEach((el) => {
    const s = getCleanText(el);
    if (s && s.length < 50 && !base.skills.includes(s)) {
      base.skills.push(s);
    }
  });

  return base;
}

function extractGenericData(base) {
  const h1 = document.querySelector('h1');
  if (h1) base.name = getCleanText(h1);

  const metaDesc = document.querySelector('meta[name="description"]');
  if (metaDesc) base.summary = metaDesc.content.trim();

  return base;
}
