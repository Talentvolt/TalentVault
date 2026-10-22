import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import { CONTENT_PATH } from "./harness.mjs";

const CONTENT_SOURCE = readFileSync(CONTENT_PATH, "utf8");

function loadExtractor(html, url = "https://www.linkedin.com/in/example/") {
  const dom = new JSDOM(html, { url, runScripts: "outside-only" });
  const { window } = dom;
  window.chrome = { runtime: { onMessage: { addListener() {} } } };
  window.scrollBy = () => {};
  window.eval(CONTENT_SOURCE);
  return window;
}

const LINKEDIN_FIXTURE = `<!DOCTYPE html><html><body>
  <h1 class="text-heading-xlarge">Ananya Deshmukh</h1>
  <div class="text-body-medium break-words">Principal AI Architect</div>
  <div class="pv-text-details__left-panel">
    <span class="text-body-small inline t-black--light break-words">Bengaluru, Karnataka, India</span>
  </div>

  <section id="experience">
    <h2>Experience</h2>
    <ul class="pvs-list">
      <li class="artdeco-list__item">
        <div class="pvs-entity">
          <div class="display-flex flex-column">
            <span class="t-bold"><span aria-hidden="true">Principal AI Architect</span></span>
            <span class="t-14 t-normal"><span aria-hidden="true">NVIDIA</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Jan 2022 - Present</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Bengaluru, India</span></span>
          </div>
          <div class="pv-shared-text-with-see-more"><span aria-hidden="true">Leads AI infrastructure for APAC.</span></div>
        </div>
      </li>
      <li class="artdeco-list__item">
        <div class="pvs-entity">
          <div class="display-flex flex-column">
            <span class="t-bold"><span aria-hidden="true">Software Engineer</span></span>
            <span class="t-14 t-normal"><span aria-hidden="true">Google</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Jun 2018 - Dec 2021</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Hyderabad, India</span></span>
          </div>
        </div>
      </li>
      <li class="artdeco-list__item">
        <div class="pvs-entity">
          <div class="display-flex"><span class="t-bold"><span aria-hidden="true">Microsoft</span></span></div>
          <ul class="pvs-list">
            <li>
              <div class="display-flex flex-column">
                <span class="t-bold"><span aria-hidden="true">Senior Engineer</span></span>
                <span class="t-14 t-normal"><span aria-hidden="true">Mar 2015 - May 2018</span></span>
                <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Redmond</span></span>
              </div>
            </li>
            <li>
              <div class="display-flex flex-column">
                <span class="t-bold"><span aria-hidden="true">Intern</span></span>
                <span class="t-14 t-normal"><span aria-hidden="true">Jun 2014 - Aug 2014</span></span>
              </div>
            </li>
          </ul>
        </div>
      </li>
    </ul>
  </section>

  <section id="education">
    <h2>Education</h2>
    <ul class="pvs-list">
      <li class="artdeco-list__item">
        <div class="display-flex flex-column">
          <span class="t-bold"><span aria-hidden="true">IISc Bangalore</span></span>
          <span class="t-14 t-normal"><span aria-hidden="true">Ph.D., Computer Science</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">2008 - 2012</span></span>
        </div>
      </li>
      <li class="artdeco-list__item">
        <div class="display-flex flex-column">
          <span class="t-bold"><span aria-hidden="true">IIT Madras</span></span>
          <span class="t-14 t-normal"><span aria-hidden="true">B.Tech, Computer Science</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">2004 - 2008</span></span>
        </div>
      </li>
    </ul>
  </section>

  <section id="skills">
    <h2>Skills</h2>
    <ul class="pvs-list">
      <li><span aria-hidden="true">Python</span></li>
      <li><span aria-hidden="true">PyTorch</span></li>
      <li><span aria-hidden="true">CUDA</span></li>
    </ul>
  </section>
</body></html>`;

test("extracts all LinkedIn experience entries including multiple roles at one company", () => {
  const window = loadExtractor(LINKEDIN_FIXTURE);
  const data = window.extractPageData();

  assert.equal(data.name, "Ananya Deshmukh");
  assert.equal(data.headline, "Principal AI Architect");
  assert.equal(data.location, "Bengaluru, Karnataka, India");
  assert.equal(data.source, "linkedin");

  // 2 single-role + 1 multi-role (2 roles) = 4 experience entries.
  assert.equal(data.experience.length, 4);

  assert.deepEqual(data.experience[0].company_name, "NVIDIA");
  assert.equal(data.experience[0].designation, "Principal AI Architect");
  assert.equal(data.experience[0].duration, "Jan 2022 - Present");
  assert.equal(data.experience[0].location, "Bengaluru, India");
  assert.match(data.experience[0].description, /AI infrastructure/);

  assert.equal(data.experience[1].company_name, "Google");
  assert.equal(data.experience[2].company_name, "Microsoft");
  assert.equal(data.experience[2].designation, "Senior Engineer");
  assert.equal(data.experience[3].company_name, "Microsoft");
  assert.equal(data.experience[3].designation, "Intern");
  assert.equal(data.experience[3].duration, "Jun 2014 - Aug 2014");

  // Education: 2 entries with degree + field split.
  assert.equal(data.education.length, 2);
  assert.equal(data.education[0].institution, "IISc Bangalore");
  assert.equal(data.education[0].degree, "Ph.D.");
  assert.equal(data.education[0].field_of_study, "Computer Science");
  assert.equal(data.education[1].institution, "IIT Madras");

  // Skills: all 3.
  assert.deepEqual(Array.from(data.skills), ["Python", "PyTorch", "CUDA"]);
});

test("returns empty arrays when experience and education sections are absent", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <h1 class="text-heading-xlarge">No Sections Person</h1>
    <div class="text-body-medium break-words">Consultant</div>
  </body></html>`);
  const data = window.extractPageData();

  assert.equal(data.name, "No Sections Person");
  assert.equal(data.experience.length, 0);
  assert.equal(data.education.length, 0);
  assert.equal(data.skills.length, 0);
});

test("does not fabricate duration or location when they are missing", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <h1 class="text-heading-xlarge">Sparse Person</h1>
    <section id="experience"><h2>Experience</h2><ul class="pvs-list">
      <li class="artdeco-list__item"><div class="pvs-entity"><div class="display-flex flex-column">
        <span class="t-bold"><span aria-hidden="true">Engineer</span></span>
        <span class="t-14 t-normal"><span aria-hidden="true">Acme Corp</span></span>
      </div></div></li>
    </ul></section>
  </body></html>`);
  const data = window.extractPageData();

  assert.equal(data.experience.length, 1);
  assert.equal(data.experience[0].company_name, "Acme Corp");
  assert.equal(data.experience[0].designation, "Engineer");
  assert.equal(data.experience[0].duration, "");
  assert.equal(data.experience[0].location, "");
});

test("extracts Naukri work experience and education entries", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="candidate-profile">
      <div class="profile-summary-card">
        <h1 class="name">Shital Pandurang Gurale</h1>
        <div class="resume-headline">Senior Software Engineer</div>
        <div class="loc">Pune, Maharashtra, India</div>
      </div>

      <section class="detail-card">
        <h3 class="section-title">Work Experience</h3>
        <ul class="exp-list">
          <li class="exp-item">
            <span class="company">AccunAI</span>
            <span class="designation">Senior Software Engineer</span>
            <span class="duration">Jan 2022 - Present</span>
            <span class="loc">Pune, India</span>
            <span class="desc">Leading platform engineering.</span>
          </li>
          <li class="exp-item">
            <span class="company">Firstsource</span>
            <span class="designation">Software Engineer</span>
            <span class="duration">Jun 2019 - Dec 2021</span>
            <span class="loc">Mumbai, India</span>
          </li>
        </ul>
      </section>

      <section class="detail-card">
        <h3 class="section-title">Education</h3>
        <ul class="edu-list">
          <li class="edu-item">
            <span class="institute">Savitribai Phule Pune University</span>
            <span class="degree">B.E., Computer Engineering</span>
            <span class="dates">2014 - 2018</span>
          </li>
        </ul>
      </section>

      <section class="detail-card">
        <h3 class="section-title">Key Skills</h3>
        <ul class="skill-list">
          <li><span>Java</span></li>
          <li><span>Spring Boot</span></li>
        </ul>
      </section>

      <aside class="sidebar similar-profiles">
        <h3>Similar Profiles</h3>
        <ul>
          <li class="exp-item">
            <span class="company">Unrelated Corp</span>
            <span class="designation">Engineer</span>
            <span class="duration">2020 - 2023</span>
          </li>
        </ul>
      </aside>
    </div>
  </body></html>`, "https://resdex.naukri.com/v3/preview?profileId=8847&_src=recruiter&ts=12345");
  const data = window.extractPageData();

  assert.equal(data.source, "naukri");
  assert.equal(data.name, "Shital Pandurang Gurale");
  assert.equal(data.headline, "Senior Software Engineer");
  assert.equal(data.location, "Pune, Maharashtra, India");

  // Canonical profile URL keeps the stable id and drops transient params.
  assert.match(data.profile_url, /profileId=8847/);
  assert.doesNotMatch(data.profile_url, /_src|ts=/);

  // Two real experience entries; the sidebar "similar profile" is excluded.
  assert.equal(data.experience.length, 2);
  assert.equal(data.experience[0].company_name, "AccunAI");
  assert.equal(data.experience[0].designation, "Senior Software Engineer");
  assert.equal(data.experience[0].duration, "Jan 2022 - Present");
  assert.equal(data.experience[0].location, "Pune, India");
  assert.match(data.experience[0].description, /platform engineering/);
  assert.equal(data.experience[1].company_name, "Firstsource");
  assert.equal(data.experience[1].designation, "Software Engineer");

  // Employment type must never be fabricated when the profile does not state it.
  assert.equal(data.experience[0].employment_type, "");
  assert.equal(data.experience[1].employment_type, "");

  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "Savitribai Phule Pune University");
  assert.equal(data.education[0].degree, "B.E.");

  assert.deepEqual(Array.from(data.skills), ["Java", "Spring Boot"]);
});

// Naukri Resdex where entries are DIV blocks (not <li>) — exercises the
// block-level fallback and verifies no sidebar contamination.
test("extracts div-based Naukri Resdex entries without sidebar contamination", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <h1 class="name">Rohan Sharma</h1>
    <div class="resume-headline">Staff Frontend Engineer</div>

    <div class="detail-card">
      <div class="section-title">Work Experience</div>
      <div class="exp-row">
        <span class="company">Atlassian</span>
        <span class="designation">Staff Frontend Engineer</span>
        <span class="duration">Jan 2021 - Present</span>
        <span class="location">Bengaluru, India</span>
      </div>
      <div class="exp-row">
        <span class="company">Flipkart</span>
        <span class="designation">Senior UI Engineer</span>
        <span class="duration">Jul 2016 - Dec 2020</span>
      </div>
    </div>

    <aside class="similar-candidates">
      <div class="exp-row">
        <span class="company">Someone Else Inc</span>
        <span class="designation">CTO</span>
        <span class="duration">2015 - Present</span>
      </div>
    </aside>
  </body></html>`, "https://resdex.naukri.com/v3/preview?id=123");
  const data = window.extractPageData();

  assert.equal(data.name, "Rohan Sharma");
  assert.equal(data.experience.length, 2);
  assert.equal(data.experience[0].company_name, "Atlassian");
  assert.equal(data.experience[1].company_name, "Flipkart");
  // Sidebar candidate is not leaked into the profile.
  for (const exp of data.experience) {
    assert.notEqual(exp.company_name, "Someone Else Inc");
  }
});

// Regression: the main candidate is "Leo Alwin S"; "Amit Goswami" is a similar-
// profile card in a right rail. The parser must return the main candidate, not
// the similar-profile name. The sidebar uses classes ("right-pane"/"prp-card")
// that do NOT match the generic exclusion keywords, so this exercises the
// heading-priority + link-exclusion logic (similar profiles are links).
test("Naukri returns the main candidate, not a similar-profile card", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="main-profile">
      <div class="profile-header">
        <h1>Leo Alwin S</h1>
        <div class="resume-headline">Senior Data Engineer</div>
        <div class="loc">Bengaluru, Karnataka, India</div>
      </div>
      <section class="detail-card">
        <h3 class="section-title">Work Experience</h3>
        <ul class="exp-list">
          <li class="exp-item">
            <span class="company">AccunAI</span>
            <span class="designation">Senior Data Engineer</span>
            <span class="duration">Jan 2022 - Present</span>
          </li>
        </ul>
      </section>
    </div>

    <div class="right-pane">
      <div class="prp-card">
        <a href="/v3/preview?profileId=222"><span class="name">Amit Goswami</span></a>
        <span class="designation">CTO</span>
      </div>
      <div class="prp-card">
        <a href="/v3/preview?profileId=333"><span class="name">Rahul Verma</span></a>
        <span class="designation">Product Manager</span>
      </div>
    </div>
  </body></html>`, "https://resdex.naukri.com/v3/preview?profileId=111");
  const data = window.extractPageData();

  assert.equal(data.name, "Leo Alwin S");
  assert.notEqual(data.name, "Amit Goswami");
  assert.notEqual(data.name, "Rahul Verma");
  assert.equal(data.experience.length, 1);
  assert.equal(data.experience[0].company_name, "AccunAI");
});

// Regression: the candidate name must come from the h1 inside <main>, never from
// a "recent search" / "similar profiles" sidebar that appears earlier in the DOM.
test("Naukri name is scoped to <main> h1, ignoring recent-search sidebar", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="recent-search">
      <h1>Samina Ansari</h1>
      <div class="designation">HR Manager</div>
    </div>

    <main class="profile-details">
      <div class="profile-header">
        <h1>Farhan Shaikh</h1>
        <div class="resume-headline">Senior Software Engineer</div>
        <div class="loc">Mumbai, India</div>
      </div>
      <h2>Work Experience</h2>
      <div class="exp-wrapper">
        <div class="exp-row"><span class="company">Siemens</span><span class="designation">Senior Software Engineer</span><span class="duration">Jan 2021 - Present</span></div>
      </div>
      <h2>Education</h2>
      <div class="edu-row"><span class="institute">Mumbai University</span><span class="degree">B.E.</span><span class="dates">2013 - 2017</span></div>
    </main>
  </body></html>`, "https://resdex.naukri.com/v3/preview?profileId=555");

  const data = window.extractPageData();

  assert.equal(data.name, "Farhan Shaikh");
  assert.notEqual(data.name, "Samina Ansari");
  assert.equal(data.experience.length, 1);
  assert.equal(data.experience[0].company_name, "Siemens");
  assert.equal(data.education.length, 1);
});

// Realistic LinkedIn DOM that does NOT use the brittle legacy classes
// (`.pvs-list`, `.t-bold`, `.t-14`, `.display-flex.flex-column`). Sections are
// found by heading text and entries by aria-hidden spans, which is what modern
// LinkedIn actually renders.
const REALISTIC_LINKEDIN = `<!DOCTYPE html><html><body>
  <h1>Meera Krishnan</h1>

  <section>
    <h2>Experience</h2>
    <div class="artdeco-card">
      <ul>
        <li>
          <div class="entity">
            <div class="col">
              <span aria-hidden="true">Staff Software Engineer</span>
              <span aria-hidden="true">Acme Corp</span>
              <span aria-hidden="true">Jan 2021 - Present</span>
              <span aria-hidden="true">Bengaluru, India</span>
            </div>
            <div class="inline-show-more-text"><span aria-hidden="true">Led platform engineering across APAC.</span></div>
          </div>
        </li>
        <li>
          <div class="entity">
            <div class="col">
              <span aria-hidden="true">Senior Engineer</span>
              <span aria-hidden="true">Globex</span>
              <span aria-hidden="true">Mar 2017 - Dec 2020</span>
              <span aria-hidden="true">Hyderabad, India</span>
            </div>
          </div>
        </li>
        <li>
          <div class="entity">
            <div class="col"><span aria-hidden="true">Initech</span></div>
            <ul>
              <li>
                <div class="col">
                  <span aria-hidden="true">Engineering Lead</span>
                  <span aria-hidden="true">Jun 2014 - Feb 2017</span>
                  <span aria-hidden="true">Pune, India</span>
                </div>
              </li>
              <li>
                <div class="col">
                  <span aria-hidden="true">Intern</span>
                  <span aria-hidden="true">Jun 2013 - May 2014</span>
                </div>
              </li>
            </ul>
          </div>
        </li>
      </ul>
    </div>
  </section>

  <section>
    <h2>Education</h2>
    <div class="artdeco-card">
      <ul>
        <li>
          <div class="col">
            <span aria-hidden="true">IIT Bombay</span>
            <span aria-hidden="true">B.Tech, Computer Science</span>
            <span aria-hidden="true">2010 - 2014</span>
          </div>
        </li>
        <li>
          <div class="col">
            <span aria-hidden="true">Delhi Public School</span>
            <span aria-hidden="true">Higher Secondary</span>
            <span aria-hidden="true">2008 - 2010</span>
          </div>
        </li>
      </ul>
    </div>
  </section>

  <section>
    <h2>Skills</h2>
    <div class="artdeco-card">
      <ul>
        <li><span aria-hidden="true">Go</span></li>
        <li><span aria-hidden="true">Rust</span></li>
      </ul>
    </div>
  </section>
</body></html>`;

test("extracts multiple work entries (incl. multi-role group) and education from realistic LinkedIn DOM", () => {
  const window = loadExtractor(REALISTIC_LINKEDIN);
  const data = window.extractPageData();

  assert.equal(data.name, "Meera Krishnan");
  assert.equal(data.source, "linkedin");

  assert.equal(data.experience.length, 4);
  assert.equal(data.experience[0].company_name, "Acme Corp");
  assert.equal(data.experience[0].designation, "Staff Software Engineer");
  assert.equal(data.experience[0].duration, "Jan 2021 - Present");
  assert.equal(data.experience[0].location, "Bengaluru, India");
  assert.match(data.experience[0].description, /platform engineering/);

  assert.equal(data.experience[1].company_name, "Globex");
  assert.equal(data.experience[1].designation, "Senior Engineer");

  assert.equal(data.experience[2].company_name, "Initech");
  assert.equal(data.experience[2].designation, "Engineering Lead");
  assert.equal(data.experience[2].location, "Pune, India");
  assert.equal(data.experience[3].company_name, "Initech");
  assert.equal(data.experience[3].designation, "Intern");

  assert.equal(data.education.length, 2);
  assert.equal(data.education[0].institution, "IIT Bombay");
  assert.equal(data.education[0].degree, "B.Tech");
  assert.equal(data.education[0].field_of_study, "Computer Science");
  assert.equal(data.education[0].dates, "2010 - 2014");
  assert.equal(data.education[1].institution, "Delhi Public School");

  assert.deepEqual(Array.from(data.skills), ["Go", "Rust"]);
});

test("returns empty arrays without fabricating data when sections are missing", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <h1>Sparse Profile</h1>
    <section>
      <h2>Activity</h2>
      <div><ul><li><span aria-hidden="true">Liked a post</span></li></ul></div>
    </section>
  </body></html>`);
  const data = window.extractPageData();

  assert.equal(data.name, "Sparse Profile");
  assert.equal(data.experience.length, 0);
  assert.equal(data.education.length, 0);
  assert.equal(data.skills.length, 0);
});

// Div-based entity markup (no <li>, no aria-hidden) to exercise the container
// and leaf-span fallback strategies against a DOM that changed away from lists.
const DIV_ENTITY_LINKEDIN = `<!DOCTYPE html><html><body>
  <h1>Div Entity Person</h1>
  <section>
    <h2>Experience</h2>
    <div class="scaffold-layout">
      <div class="pvs-entity">
        <div class="row">
          <span class="t-bold">Backend Engineer</span>
          <span class="t-14">Contoso</span>
          <span class="t-14">Feb 2019 - Aug 2021</span>
          <span class="t-14">Remote</span>
        </div>
        <div class="inline-show-more-text"><span>Built REST APIs at scale.</span></div>
      </div>
      <div class="pvs-entity">
        <div class="row">
          <span class="t-bold">Junior Engineer</span>
          <span class="t-14">Contoso</span>
          <span class="t-14">Jul 2017 - Jan 2019</span>
        </div>
      </div>
    </div>
  </section>
  <section>
    <h2>Education</h2>
    <div class="scaffold-layout">
      <div class="pvs-entity">
        <div class="row">
          <span class="t-bold">MIT</span>
          <span class="t-14">B.S., Computer Science</span>
          <span class="t-14">2013 - 2017</span>
        </div>
      </div>
    </div>
  </section>
  <section>
    <h2>Skills</h2>
    <div class="scaffold-layout"><span class="skill">Java</span><span class="skill">Go</span></div>
  </section>
</body></html>`;

test("extracts entries from div-based entities without <li> or aria-hidden", () => {
  const window = loadExtractor(DIV_ENTITY_LINKEDIN);
  const data = window.extractPageData();

  assert.equal(data.name, "Div Entity Person");
  assert.equal(data.experience.length, 2);
  assert.equal(data.experience[0].company_name, "Contoso");
  assert.equal(data.experience[0].designation, "Backend Engineer");
  assert.equal(data.experience[0].duration, "Feb 2019 - Aug 2021");
  assert.equal(data.experience[0].location, "Remote");
  assert.match(data.experience[0].description, /REST APIs/);
  assert.equal(data.experience[1].designation, "Junior Engineer");

  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "MIT");
  assert.equal(data.education[0].degree, "B.S.");
  assert.equal(data.education[0].field_of_study, "Computer Science");
});

// Reproduces the reported "Company: Not Specified" / "Designation: Present"
// bug: split date fragments and an employment-type suffix must never leak into
// company or designation fields.
const SPLIT_DATE_LINKEDIN = `<!DOCTYPE html><html><body>
  <h1>Split Date Person</h1>
  <section>
    <h2>Experience</h2>
    <ul class="pvs-list">
      <li class="artdeco-list__item">
        <div class="pvs-entity">
          <div class="display-flex flex-column">
            <span class="t-bold"><span aria-hidden="true">Senior Engineer</span></span>
            <span class="t-14 t-normal"><span aria-hidden="true">Google · Full-time</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Mar 2018 - </span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Present</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">5 yrs 9 mos</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Bengaluru, India</span></span>
          </div>
        </div>
      </li>
    </ul>
  </section>
</body></html>`;

test("maps company/designation correctly with split dates and employment type", () => {
  const window = loadExtractor(SPLIT_DATE_LINKEDIN);
  const data = window.extractPageData();

  assert.equal(data.experience.length, 1);
  const exp = data.experience[0];

  assert.equal(exp.company_name, "Google");
  assert.equal(exp.designation, "Senior Engineer");
  assert.equal(exp.employment_type, "Full-time");
  assert.equal(exp.location, "Bengaluru, India");
  assert.match(exp.duration, /Mar 2018 - Present/);

  // No reserved words may leak into company or designation.
  assert.doesNotMatch(exp.company_name, /present|full[-\s]?time|more|not specified/i);
  assert.doesNotMatch(exp.designation, /present|full[-\s]?time|more|not specified/i);
});

test("detects an available resume link on a Naukri profile", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <h1 class="user-name">Resume Person</h1>
    <a href="/mnjuser/download-resume.pdf" aria-label="Download Resume">Download Resume</a>
  </body></html>`, "https://www.naukri.com/mnjuser/profile?id=1");
  const data = window.extractPageData();

  assert.equal(data.resume_available, true);
  assert.match(data.resume_url, /download-resume\.pdf/);
  assert.equal(data.resume_filename, "download-resume.pdf");
});

test("reports no resume when none is present", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <h1 class="user-name">No Resume Person</h1>
    <a href="/profile/summary">View Profile</a>
  </body></html>`, "https://www.naukri.com/mnjuser/profile?id=2");
  const data = window.extractPageData();

  assert.equal(data.resume_available, false);
  assert.equal(data.resume_url, "");
});

// Headings and their list entries as SIBLINGS (no <section>, no id) — exercises
// the DOM-agnostic heading-region fallback that locates entries up to the next
// heading.
const SIBLING_HEADING_LINKEDIN = `<!DOCTYPE html><html><body>
  <h1 class="text-heading-xlarge">Region Person</h1>
  <div class="profile-scaffold">
    <h2>Experience</h2>
    <ul>
      <li class="artdeco-list__item">
        <div class="display-flex flex-column">
          <span class="t-bold"><span aria-hidden="true">Staff Engineer</span></span>
          <span class="t-14 t-normal"><span aria-hidden="true">Acme</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">2020 - Present</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Remote</span></span>
        </div>
      </li>
    </ul>
    <h2>Education</h2>
    <ul>
      <li class="artdeco-list__item">
        <div class="display-flex flex-column">
          <span class="t-bold"><span aria-hidden="true">IIT Delhi</span></span>
          <span class="t-14 t-normal"><span aria-hidden="true">B.Tech</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">2015 - 2019</span></span>
        </div>
      </li>
    </ul>
  </div>
</body></html>`;

test("extracts entries from sibling heading regions without <section> or id", () => {
  const window = loadExtractor(SIBLING_HEADING_LINKEDIN);
  const data = window.extractPageData();

  assert.equal(data.name, "Region Person");
  assert.equal(data.experience.length, 1);
  assert.equal(data.experience[0].company_name, "Acme");
  assert.equal(data.experience[0].designation, "Staff Engineer");
  assert.equal(data.experience[0].duration, "2020 - Present");

  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "IIT Delhi");
  assert.equal(data.education[0].degree, "B.Tech");
});

// Real-browser shape where the section title is NOT an <h2> (a plain <div>),
// which previously made findHeadingElement return null.
const DIV_TITLE_LINKEDIN = `<!DOCTYPE html><html><body>
  <h1 class="text-heading-xlarge">Div Title Person</h1>
  <div class="artdeco-card">
    <div class="pvs-header__title-container"><div class="title">Experience</div></div>
    <ul>
      <li class="artdeco-list__item">
        <div class="display-flex flex-column">
          <span class="t-bold"><span aria-hidden="true">Lead Developer</span></span>
          <span class="t-14 t-normal"><span aria-hidden="true">Acme</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Jan 2021 - Present</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Remote</span></span>
        </div>
      </li>
    </ul>
  </div>
  <div class="artdeco-card">
    <div class="pvs-header__title-container"><div class="title">Education</div></div>
    <ul>
      <li class="artdeco-list__item">
        <div class="display-flex flex-column">
          <span class="t-bold"><span aria-hidden="true">IIT Bombay</span></span>
          <span class="t-14 t-normal"><span aria-hidden="true">B.Tech, CS</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">2012 - 2016</span></span>
        </div>
      </li>
    </ul>
  </div>
</body></html>`;

test("extracts entries when section titles are plain divs, not headings", () => {
  const window = loadExtractor(DIV_TITLE_LINKEDIN);
  const data = window.extractPageData();

  assert.equal(data.name, "Div Title Person");
  assert.equal(data.experience.length, 1);
  assert.equal(data.experience[0].company_name, "Acme");
  assert.equal(data.experience[0].designation, "Lead Developer");
  assert.equal(data.experience[0].duration, "Jan 2021 - Present");

  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "IIT Bombay");
  assert.equal(data.education[0].degree, "B.Tech");
});

// Regression: Naukri's ".mid-detail" "Current" label (value in a sibling), plus
// "h2 heading + sibling container" section layout with terse class names (no
// ".company"/".designation" classes). Exercises the label-value current parser
// and the line-based entry fallback.
test("Naukri parses 'Current' label + h2/sibling sections with terse classes", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="profile-details">
      <h1 class="name">VARUN DUBEY</h1>
      <div class="loc">Delhi, India</div>
      <div class="mid-detail">
        <span class="detail-label">Current</span>
        <span class="detail-value">Full Stack Developer at Mediacile</span>
      </div>
      <h2>Work Experience</h2>
      <div class="exp-wrapper">
        <div class="row"><div class="t">Full Stack Developer</div><div class="c">Mediacile</div><div class="d">Jan 2021 - Present</div></div>
        <div class="row"><div class="t">Engineer</div><div class="c">Infosys</div><div class="d">Jun 2018 - Dec 2020</div></div>
      </div>
      <h2>Education</h2>
      <div class="edu-wrapper">
        <div class="row"><div class="n">IIT Delhi</div><div class="g">B.Tech</div><div class="y">2014 - 2018</div></div>
      </div>
    </div>
  </body></html>`, "https://resdex.naukri.com/v3/preview?profileId=55");

  const data = window.extractPageData();

  assert.equal(data.name, "VARUN DUBEY");
  assert.equal(data.current_company, "Mediacile");
  assert.equal(data.current_designation, "Full Stack Developer");

  assert.equal(data.experience.length, 2);
  assert.equal(data.experience[0].company_name, "Mediacile");
  assert.equal(data.experience[0].designation, "Full Stack Developer");
  assert.equal(data.experience[0].duration, "Jan 2021 - Present");
  assert.equal(data.experience[1].company_name, "Infosys");
  assert.equal(data.experience[1].designation, "Engineer");

  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "IIT Delhi");
  assert.equal(data.education[0].degree, "B.Tech");
  assert.equal(data.education[0].dates, "2014 - 2018");
});

// Regression: the Naukri header lists "Current:"/"Previous:" plus "Highest degree"
// and "Pref. location". The designation must come from the "Current"/"Previous"
// value split on " at ", never from the "Highest degree" institute text.
test("Naukri header parses 'Current:' designation and never grabs 'Highest degree'", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="profile-details">
      <div class="profile-header">
        <h1 class="name">Varun Dubey</h1>
        <div class="email">varundubey21091997@gmail.com</div>
        <div class="current">Current: Python Developer at Siemens</div>
        <div class="prev">Previous: Software Engineer at Experion</div>
        <div class="degree">Highest degree: B.Tech - GLA Institute of Technology and Management, Mathura</div>
        <div class="pref">Pref. location: Noida</div>
      </div>
    </div>
  </body></html>`, "https://resdex.naukri.com/v3/preview?profileId=77");

  const data = window.extractPageData();

  assert.equal(data.current_designation, "Python Developer");
  assert.equal(data.current_company, "Siemens");
  assert.notEqual(data.current_designation, "GLA Institute of Technology and Management, Mathura");
  assert.equal(data.email, "varundubey21091997@gmail.com");
});

// Regression: Naukri "Personal details" / "Other details" (DOB, gender, category)
// must never leak into the Work Experience list.
test("Naukri experience excludes personal details (DOB/Gender/Category)", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="profile-details">
      <h1 class="name">Varun Dubey</h1>
      <div class="resume-headline">Python Developer</div>
      <div class="loc">Noida, India</div>

      <h2>Work Experience</h2>
      <div class="exp-wrapper">
        <div class="exp-row"><span class="company">Siemens</span><span class="designation">Python Developer</span><span class="duration">Jan 2021 - Present</span></div>
        <div class="exp-row"><span class="company">Experion</span><span class="designation">Software Engineer</span><span class="duration">Jun 2018 - Dec 2020</span></div>
      </div>

      <h2>Education</h2>
      <div class="edu-row"><span class="institute">GLA University</span><span class="degree">B.Tech</span><span class="dates">2014 - 2018</span></div>

      <h2>Personal Details</h2>
      <div class="personal-block">
        <div class="row">Date of Birth</div>
        <div class="row">1 Jun 1999</div>
        <div class="row">Gender</div>
        <div class="row">Male</div>
        <div class="row">Category</div>
        <div class="row">OBC - Creamy</div>
      </div>

      <h2>Other Details</h2>
      <div class="other-block">
        <div class="row">Marital Status</div>
        <div class="row">Single</div>
      </div>
    </div>
  </body></html>`, "https://resdex.naukri.com/v3/preview?profileId=88");

  const data = window.extractPageData();

  assert.equal(data.experience.length, 2);
  assert.equal(data.experience[0].company_name, "Siemens");
  assert.equal(data.experience[1].company_name, "Experion");
  for (const exp of data.experience) {
    assert.doesNotMatch(exp.designation + " " + exp.company_name, /Date of Birth|Gender|Category|Male|OBC|Marital/i);
  }
  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "GLA University");
});

const REALISTIC_MODERN_LINKEDIN = `<!DOCTYPE html><html><body>
<main class="scaffold-layout__main">
  <!-- Top Card -->
  <section class="artdeco-card pv-top-card">
    <div class="ph5 pb5">
      <div class="pv-text-details__left-panel">
        <h1 class="text-heading-xlarge inline t-24 v-align-middle break-words">Rajesh Sharma</h1>
        <div class="text-body-medium break-words">Principal Cloud Architect | Ex-AWS</div>
        <div class="pb2 pv-text-details__left-panel">
          <span class="text-body-small inline t-black--light break-words">Bengaluru, Karnataka, India</span>
          <span class="text-body-small inline"><a href="#contact-info">Contact info</a></span>
        </div>
      </div>
      <ul class="pv-text-details__right-panel">
        <li class="pv-text-details__right-panel-item">
          <button class="pv-text-details__right-panel-item-link" aria-label="Current company: CloudScale Systems. Click to skip to experience section">
            <span aria-hidden="true">CloudScale Systems</span>
          </button>
        </li>
        <li class="pv-text-details__right-panel-item">
          <button class="pv-text-details__right-panel-item-link" aria-label="Education: IIT Delhi. Click to skip to education section">
            <span aria-hidden="true">IIT Delhi</span>
          </button>
        </li>
      </ul>
    </div>
  </section>

  <!-- About Section -->
  <section class="artdeco-card">
    <div id="about" class="pv-profile-card__anchor"></div>
    <div class="pvs-header__container">
      <h2 class="pvs-header__title"><span aria-hidden="true">About</span></h2>
    </div>
    <div class="pv-shared-text-with-see-more">
      <span aria-hidden="true">15+ years architecting enterprise distributed cloud infrastructure.</span>
    </div>
  </section>

  <!-- Experience Section -->
  <section class="artdeco-card">
    <div id="experience" class="pv-profile-card__anchor"></div>
    <div class="pvs-header__container">
      <h2 class="pvs-header__title">
        <span aria-hidden="true">Experience</span>
        <span class="visually-hidden">Experience</span>
      </h2>
    </div>
    <ul class="pvs-list">
      <!-- Entry 1: Single role with nested SKILLS list! Must NOT be misclassified as multi-role -->
      <li class="artdeco-list__item">
        <div class="pvs-entity">
          <div class="display-flex flex-column">
            <span class="t-bold"><span aria-hidden="true">Principal Cloud Architect</span></span>
            <span class="t-14 t-normal"><span aria-hidden="true">CloudScale Systems · Full-time</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Jan 2022 - Present · 2 yrs 4 mos</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Bengaluru, Karnataka, India · Hybrid</span></span>
          </div>
          <div class="pv-shared-text-with-see-more">
            <span aria-hidden="true">Leading multi-region cloud modernization and Kubernetes platforms.</span>
          </div>
          <div class="pvs-list__outer-container">
            <ul class="pvs-list">
              <li class="pvs-list__item--with-top-padding">
                <span aria-hidden="true">Skills: Kubernetes · Terraform · AWS · Go</span>
              </li>
            </ul>
          </div>
        </div>
      </li>

      <!-- Entry 2: Multi-role at Amazon (2 roles) -->
      <li class="artdeco-list__item">
        <div class="pvs-entity">
          <div class="display-flex flex-column">
            <span class="t-bold"><span aria-hidden="true">Amazon Web Services (AWS)</span></span>
            <span class="t-14 t-normal"><span aria-hidden="true">Full-time · 5 yrs 6 mos</span></span>
          </div>
          <ul class="pvs-list">
            <li class="pvs-list__item--with-top-padding">
              <div class="display-flex flex-column">
                <span class="t-bold"><span aria-hidden="true">Senior Cloud Solutions Architect</span></span>
                <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Mar 2019 - Dec 2021 · 2 yrs 10 mos</span></span>
                <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Hyderabad, India</span></span>
              </div>
              <div class="pv-shared-text-with-see-more">
                <span aria-hidden="true">Designed serverless microservices for tier-1 enterprises.</span>
              </div>
            </li>
            <li class="pvs-list__item--with-top-padding">
              <div class="display-flex flex-column">
                <span class="t-bold"><span aria-hidden="true">Cloud Solutions Architect</span></span>
                <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Jul 2016 - Feb 2019 · 2 yrs 8 mos</span></span>
                <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Bengaluru, India</span></span>
              </div>
            </li>
          </ul>
        </div>
      </li>
    </ul>
  </section>

  <!-- Education Section -->
  <section class="artdeco-card">
    <div id="education" class="pv-profile-card__anchor"></div>
    <div class="pvs-header__container">
      <h2 class="pvs-header__title">
        <span aria-hidden="true">Education</span>
        <span class="visually-hidden">Education</span>
      </h2>
    </div>
    <ul class="pvs-list">
      <li class="artdeco-list__item">
        <div class="display-flex flex-column">
          <span class="t-bold"><span aria-hidden="true">Indian Institute of Technology, Delhi</span></span>
          <span class="t-14 t-normal"><span aria-hidden="true">B.Tech, Computer Science and Engineering</span></span>
          <span class="t-14 t-normal t-black--light"><span aria-hidden="true">2012 - 2016</span></span>
        </div>
      </li>
    </ul>
  </section>
</main>
</body></html>`;

test("extracts realistic modern LinkedIn profile with right panel company, nested skills, and multi-role", () => {
  const window = loadExtractor(REALISTIC_MODERN_LINKEDIN, "https://www.linkedin.com/in/rajesh-sharma/");
  const data = window.extractPageData();

  assert.equal(data.name, "Rajesh Sharma");
  assert.equal(data.headline, "Principal Cloud Architect | Ex-AWS");
  assert.equal(data.current_company, "CloudScale Systems");
  assert.equal(data.location, "Bengaluru, Karnataka, India");
  assert.match(data.summary, /15\+ years architecting/);

  // 1 single-role (with nested skills) + 1 multi-role (2 positions) = 3 total
  assert.equal(data.experience.length, 3);

  // Entry 1: Single role
  assert.equal(data.experience[0].company_name, "CloudScale Systems");
  assert.equal(data.experience[0].designation, "Principal Cloud Architect");
  assert.equal(data.experience[0].employment_type, "Full-time");
  assert.match(data.experience[0].duration, /Jan 2022 - Present/);
  assert.match(data.experience[0].location, /Bengaluru/);
  assert.match(data.experience[0].description, /cloud modernization/);

  // Entry 2: Amazon Senior
  assert.equal(data.experience[1].company_name, "Amazon Web Services (AWS)");
  assert.equal(data.experience[1].designation, "Senior Cloud Solutions Architect");
  assert.match(data.experience[1].duration, /Mar 2019 - Dec 2021/);
  assert.match(data.experience[1].description, /serverless microservices/);

  // Entry 3: Amazon Solutions Architect
  assert.equal(data.experience[2].company_name, "Amazon Web Services (AWS)");
  assert.equal(data.experience[2].designation, "Cloud Solutions Architect");
  assert.match(data.experience[2].duration, /Jul 2016 - Feb 2019/);

  // Forbidden words check
  for (const exp of data.experience) {
    assert.doesNotMatch(exp.company_name, /^(present|full[-\s]?time|more)$/i);
    assert.doesNotMatch(exp.designation, /^(present|full[-\s]?time|more)$/i);
  }

  // Education
  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "Indian Institute of Technology, Delhi");
  assert.equal(data.education[0].degree, "B.Tech");
  assert.equal(data.education[0].field_of_study, "Computer Science and Engineering");
  assert.equal(data.education[0].dates, "2012 - 2016");
});

test("extracts Naukri resume with download attribute filename", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <h1 class="user-name">Priya Nair</h1>
    <div class="resume-container">
      <a href="/recruiter/download/doc?id=8847" download="Priya_Nair_Resume_2026.pdf" aria-label="Download Candidate Resume">
        <span class="resume-name">Priya_Nair_Resume_2026.pdf</span>
      </a>
    </div>
  </body></html>`, "https://www.naukri.com/mnjuser/profile?id=8847");
  const data = window.extractPageData();

  assert.equal(data.resume_available, true);
  assert.equal(data.resume_filename, "Priya_Nair_Resume_2026.pdf");
});

test("regression: handles modern LinkedIn DOM where .inline-show-more-text wraps titles and companies", () => {
  const html = `<!DOCTYPE html><html><body>
    <h1 class="text-heading-xlarge">Modern DOM Person</h1>
    <section id="experience">
      <h2>Experience</h2>
      <ul class="pvs-list">
        <li class="artdeco-list__item">
          <div class="pvs-entity">
            <div class="display-flex flex-column">
              <div class="display-flex flex-row justify-space-between">
                <span class="t-bold">
                  <span class="inline-show-more-text inline-show-more-text--is-collapsed" aria-hidden="true">
                    Staff Machine Learning Engineer
                  </span>
                </span>
              </div>
              <span class="t-14 t-normal">
                <span class="inline-show-more-text" aria-hidden="true">Meta · Full-time</span>
              </span>
              <span class="t-14 t-normal t-black--light">
                <span class="inline-show-more-text" aria-hidden="true">Mar 2021 - Present · 3 yrs 2 mos</span>
              </span>
              <span class="t-14 t-normal t-black--light">
                <span class="inline-show-more-text" aria-hidden="true">Menlo Park, CA</span>
              </span>
            </div>
            <div class="pv-shared-text-with-see-more">
              <span class="inline-show-more-text" aria-hidden="true">Developing foundation models for ranking systems.</span>
            </div>
          </div>
        </li>
      </ul>
    </section>
    <section id="education">
      <h2>Education</h2>
      <ul class="pvs-list">
        <li class="artdeco-list__item">
          <div class="display-flex flex-column">
            <span class="t-bold">
              <span class="inline-show-more-text" aria-hidden="true">Stanford University</span>
            </span>
            <span class="t-14 t-normal">
              <span class="inline-show-more-text" aria-hidden="true">Master of Science, AI</span>
            </span>
            <span class="t-14 t-normal t-black--light">
              <span class="inline-show-more-text" aria-hidden="true">2018 - 2020</span>
            </span>
          </div>
        </li>
      </ul>
    </section>
  </body></html>`;

  const window = loadExtractor(html, "https://www.linkedin.com/in/modern-dom/");
  const data = window.extractPageData();

  assert.equal(data.experience.length, 1);
  assert.equal(data.experience[0].company_name, "Meta");
  assert.equal(data.experience[0].designation, "Staff Machine Learning Engineer");
  assert.match(data.experience[0].duration, /Mar 2021 - Present/);
  assert.equal(data.experience[0].location, "Menlo Park, CA");
  assert.match(data.experience[0].description, /foundation models/);

  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "Stanford University");
  assert.equal(data.education[0].degree, "Master of Science");
  assert.equal(data.education[0].field_of_study, "AI");
});

test("extracts projects and certifications from LinkedIn sections", () => {
  const html = `<!DOCTYPE html><html><body>
    <h1 class="text-heading-xlarge">Multifaceted Engineer</h1>
    <section id="experience">
      <h2>Experience</h2>
      <ul class="pvs-list">
        <li class="artdeco-list__item">
          <div class="pvs-entity">
            <span class="t-bold"><span aria-hidden="true">Staff Engineer</span></span>
            <span class="t-14 t-normal"><span aria-hidden="true">Google</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">2020 - Present</span></span>
          </div>
        </li>
      </ul>
    </section>
    <section id="projects">
      <h2>Projects</h2>
      <ul class="pvs-list">
        <li class="artdeco-list__item">
          <div class="display-flex flex-column">
            <span class="t-bold"><span aria-hidden="true">Talent Vault Platform</span></span>
            <span class="t-14 t-normal"><span aria-hidden="true">Lead Architect</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Jan 2023 - Present</span></span>
          </div>
          <div class="pv-shared-text-with-see-more">
            <span aria-hidden="true">AI recruitment and candidate matching system.</span>
          </div>
        </li>
      </ul>
    </section>
    <section id="licenses_and_certifications">
      <h2>Licenses &amp; certifications</h2>
      <ul class="pvs-list">
        <li class="artdeco-list__item">
          <div class="display-flex flex-column">
            <span class="t-bold"><span aria-hidden="true">AWS Certified Solutions Architect – Professional</span></span>
            <span class="t-14 t-normal"><span aria-hidden="true">Amazon Web Services (AWS)</span></span>
            <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Issued Nov 2023 · Expires Nov 2026</span></span>
          </div>
        </li>
      </ul>
    </section>
  </body></html>`;

  const window = loadExtractor(html, "https://www.linkedin.com/in/multifaceted/");
  const data = window.extractPageData();

  assert.equal(data.projects.length, 1);
  assert.equal(data.projects[0].name, "Talent Vault Platform");
  assert.equal(data.projects[0].role, "Lead Architect");
  assert.match(data.projects[0].duration, /Jan 2023 - Present/);
  assert.match(data.projects[0].description, /AI recruitment/);

  assert.equal(data.certifications.length, 1);
  assert.match(data.certifications[0].name, /AWS Certified Solutions Architect/);
  assert.equal(data.certifications[0].issuer, "Amazon Web Services (AWS)");
  assert.match(data.certifications[0].issue_date, /2023-11|Nov 2023/);
});

// Reproduces the live failure where there is NO section heading text and NO
// "#experience"/"#education" anchor — only company/school links + entry markup.
// The link-based fallback must still recover the entries.
test("recovers experience and education via company/school links when headings are absent", () => {
  const html = `<!DOCTYPE html><html><body>
    <h1 class="text-heading-xlarge">Link Only Person</h1>
    <div class="scaffold">
      <ul class="pvs-list">
        <li class="artdeco-list__item">
          <div class="pvs-entity">
            <a href="/company/acme/"><img alt=""></a>
            <div class="display-flex flex-column">
              <span class="t-bold"><span aria-hidden="true">Staff Engineer</span></span>
              <span class="t-14 t-normal"><span aria-hidden="true">Acme Corp</span></span>
              <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Jan 2021 - Present</span></span>
              <span class="t-14 t-normal t-black--light"><span aria-hidden="true">Bengaluru, India</span></span>
            </div>
          </div>
        </li>
        <li class="artdeco-list__item">
          <div class="pvs-entity">
            <a href="/school/iitb/"><img alt=""></a>
            <div class="display-flex flex-column">
              <span class="t-bold"><span aria-hidden="true">IIT Bombay</span></span>
              <span class="t-14 t-normal"><span aria-hidden="true">B.Tech, Computer Science</span></span>
              <span class="t-14 t-normal t-black--light"><span aria-hidden="true">2010 - 2014</span></span>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </body></html>`;

  const window = loadExtractor(html, "https://www.linkedin.com/in/link-only/");
  const data = window.extractPageData();

  assert.equal(data.name, "Link Only Person");
  assert.equal(data.experience.length, 1);
  assert.equal(data.experience[0].company_name, "Acme Corp");
  assert.equal(data.experience[0].designation, "Staff Engineer");
  assert.equal(data.experience[0].duration, "Jan 2021 - Present");
  assert.equal(data.experience[0].location, "Bengaluru, India");

  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "IIT Bombay");
  assert.equal(data.education[0].degree, "B.Tech");
  assert.equal(data.education[0].field_of_study, "Computer Science");
});

// Regression (Bug 1): a "Professional Summary" paragraph containing "15 years"
// must never be parsed as a Work Experience entry, and the Company field must
// never become a stray word like "Full" from "Full-time".
test("Naukri does not leak the Professional Summary into Work Experience", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="candidate-card">
      <h1 class="name">Gaurav Vyas</h1>
      <div class="resume-headline">Senior Software Engineer</div>
      <div class="loc">Pune, Maharashtra, India</div>

      <div class="section-title">Profile Summary</div>
      <div class="summary-text">Certified engineer with 15 years of experience building scalable systems and leading cross-functional teams to success.</div>

      <div class="section-title">Work Experience</div>
      <div class="exp-row">
        <span class="company">Infosys</span>
        <span class="designation">Senior Software Engineer</span>
        <span class="duration">Jan 2020 - Present · Full-time</span>
      </div>
      <div class="exp-row">
        <span class="company">TCS</span>
        <span class="designation">Software Engineer</span>
        <span class="duration">Jun 2016 - Dec 2019</span>
      </div>
    </div>
  </body></html>`, "https://resdex.naukri.com/v3/preview?sid=111");

  const data = window.extractPageData();

  assert.equal(data.name, "Gaurav Vyas");
  assert.equal(data.headline, "Senior Software Engineer");

  // Only the two real entries; the summary paragraph is NOT an entry.
  assert.equal(data.experience.length, 2);
  assert.equal(data.experience[0].company_name, "Infosys");
  assert.equal(data.experience[0].designation, "Senior Software Engineer");
  assert.equal(data.experience[1].company_name, "TCS");

  // No stray "Full" company, and no summary text bled into any entry.
  for (const exp of data.experience) {
    assert.notEqual(exp.company_name, "Full");
    assert.doesNotMatch(exp.description || "", /15 years/);
  }
});

// Regression (Bug 1): a similar-profile card ("NITISH KUMAR · Software Eng")
// must never override the candidate's own headline.
test("Naukri headline ignores similar-profile cards in the right rail", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="main-profile">
      <h1>Gaurav Vyas</h1>
      <div class="resume-headline">Senior Software Engineer</div>
      <div class="loc">Pune, Maharashtra, India</div>

      <div class="section-title">Work Experience</div>
      <div class="exp-row">
        <span class="company">Infosys</span>
        <span class="designation">Senior Software Engineer</span>
        <span class="duration">Jan 2020 - Present</span>
      </div>
    </div>

    <div class="prp-card">
      <div class="candidate-headline">NITISH KUMAR Software Eng</div>
    </div>
  </body></html>`, "https://resdex.naukri.com/v3/preview?sid=222");

  const data = window.extractPageData();

  assert.equal(data.name, "Gaurav Vyas");
  assert.equal(data.headline, "Senior Software Engineer");
  assert.notEqual(data.headline, "NITISH KUMAR Software Eng");
});

// Regression: the "similar profiles" right rail is rendered BEFORE the main
// candidate panel in document order. The parser must scope to the main
// container and never read the sidebar's headline/location, must parse the
// "Current: <Role> at <Company>" header, and must recover DIV-based education
// entries (not just <li> items).
test("Naukri scopes to main container and parses current employment + div-based education", () => {
  const window = loadExtractor(`<!DOCTYPE html><html><body>
    <div class="right-pane">
      <div class="prp-card">
        <div class="candidate-headline">NITISH KUMAR Software Eng</div>
        <div class="location">Bengaluru (prefers Bengaluru)</div>
      </div>
    </div>
    <div class="profile-details">
      <div class="profile-header">
        <h1 class="name">Gaurav Vyas</h1>
        <div class="resume-headline">Senior Software Engineer</div>
        <div class="loc">Pune, Maharashtra, India</div>
        <div class="current-org">Current: Full Stack Developer at Mediacile</div>
      </div>
      <section class="experience-section">
        <h3 class="section-title">Work Experience</h3>
        <div class="exp-row">
          <span class="company">Mediacile</span>
          <span class="designation">Full Stack Developer</span>
          <span class="duration">Jan 2021 - Present</span>
        </div>
      </section>
      <section class="education-section">
        <h3 class="section-title">Education</h3>
        <div class="edu-row">
          <span class="institute">IIT Delhi</span>
          <span class="degree">B.Tech</span>
          <span class="dates">2014 - 2018</span>
        </div>
      </section>
    </div>
  </body></html>`, "https://resdex.naukri.com/v3/preview?profileId=999");

  const data = window.extractPageData();

  assert.equal(data.name, "Gaurav Vyas");
  assert.equal(data.headline, "Senior Software Engineer");
  assert.notEqual(data.headline, "NITISH KUMAR Software Eng");
  assert.equal(data.location, "Pune, Maharashtra, India");
  assert.notEqual(data.location, "Bengaluru (prefers Bengaluru)");

  // "Current: Full Stack Developer at Mediacile" is split into both fields.
  assert.equal(data.current_company, "Mediacile");
  assert.equal(data.current_designation, "Full Stack Developer");

  assert.equal(data.experience.length, 1);
  assert.equal(data.experience[0].company_name, "Mediacile");
  assert.equal(data.experience[0].designation, "Full Stack Developer");

  assert.equal(data.education.length, 1);
  assert.equal(data.education[0].institution, "IIT Delhi");
  assert.equal(data.education[0].degree, "B.Tech");
});


