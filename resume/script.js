document.getElementById("year").textContent = new Date().getFullYear();

/* Theme toggle */
const themeToggle = document.getElementById("themeToggle");
const root = document.documentElement;
const savedTheme = localStorage.getItem("theme");
const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

if (savedTheme === "dark" || (!savedTheme && prefersDark)) {
  root.setAttribute("data-theme", "dark");
}

themeToggle.addEventListener("click", () => {
  const isDark = root.getAttribute("data-theme") === "dark";
  if (isDark) {
    root.removeAttribute("data-theme");
    localStorage.setItem("theme", "light");
  } else {
    root.setAttribute("data-theme", "dark");
    localStorage.setItem("theme", "dark");
  }
});

/* Mobile nav toggle */
const navToggle = document.getElementById("navToggle");
const navLinks = document.getElementById("navLinks");

navToggle.addEventListener("click", () => {
  const isOpen = navLinks.classList.toggle("open");
  navToggle.setAttribute("aria-expanded", String(isOpen));
});

navLinks.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    navLinks.classList.remove("open");
    navToggle.setAttribute("aria-expanded", "false");
  });
});

/* Card detail panels: clicking a card in a grid opens a shared panel under
   the section heading (not an inline dropdown), hiding the grid until the
   explicit close button is used. Reused for both Expertise and Projects. */
function setupDetailPanel({ layoutId, listId, detailId, titleId, tagsId, bodyId, closeId }) {
  const layout = document.getElementById(layoutId);
  const list = document.getElementById(listId);
  const detail = document.getElementById(detailId);
  const titleEl = document.getElementById(titleId);
  const tagsEl = document.getElementById(tagsId);
  const bodyEl = document.getElementById(bodyId);
  const closeBtn = document.getElementById(closeId);
  const triggers = list.querySelectorAll(".expertise-trigger");

  function close() {
    detail.hidden = true;
    triggers.forEach((btn) => btn.setAttribute("aria-expanded", "false"));
    layout.classList.remove("detail-open");
  }

  function open(trigger) {
    if (trigger.getAttribute("aria-expanded") === "true") {
      close();
      return;
    }

    const template = document.getElementById(trigger.dataset.target);
    titleEl.textContent = trigger.querySelector("h3").textContent;
    tagsEl.textContent = trigger.querySelector(".project-tags").textContent;

    triggers.forEach((btn) => btn.setAttribute("aria-expanded", "false"));
    trigger.setAttribute("aria-expanded", "true");

    bodyEl.innerHTML = "";
    bodyEl.appendChild(template.content.cloneNode(true));

    detail.hidden = false;
    layout.classList.add("detail-open");
    detail.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  triggers.forEach((trigger) => trigger.addEventListener("click", () => open(trigger)));
  if (closeBtn) closeBtn.addEventListener("click", close);

  return { close };
}

const expertiseDetailPanel = setupDetailPanel({
  layoutId: "expertiseLayout",
  listId: "expertiseList",
  detailId: "expertiseDetail",
  titleId: "expertiseDetailTitle",
  tagsId: "expertiseDetailTags",
  bodyId: "expertiseDetailList",
  closeId: "expertiseDetailClose",
});

const projectsDetailPanel = setupDetailPanel({
  layoutId: "projectsLayout",
  listId: "projectsList",
  detailId: "projectDetail",
  titleId: "projectDetailTitle",
  tagsId: "projectDetailTags",
  bodyId: "projectDetailBody",
  closeId: "projectDetailClose",
});

/* Tabbed sections: clicking a nav link swaps which panel is visible
   instead of scrolling to it, so only one section renders at a time. */
const panels = document.querySelectorAll("main > .section");
const panelMap = new Map();
panels.forEach((panel) => panelMap.set(panel.id, panel));

const navLinkMap = new Map();
navLinks.querySelectorAll("a").forEach((a) => {
  navLinkMap.set(a.getAttribute("href").slice(1), a);
});

function showPanel(id, { updateHash = true, scroll = true } = {}) {
  const panel = panelMap.get(id) || panels[0];

  panels.forEach((p) => p.classList.toggle("active-panel", p === panel));
  navLinks.querySelectorAll("a").forEach((a) => a.classList.remove("active"));
  const link = navLinkMap.get(panel.id);
  if (link) link.classList.add("active");

  document.body.classList.toggle("hero-locked", panel.id === "about" || panel.id === "now");

  expertiseDetailPanel.close();
  projectsDetailPanel.close();

  if (updateHash) {
    history.pushState(null, "", "#" + panel.id);
  }
  if (scroll) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href^="#"]');
  if (!link) return;
  const id = link.getAttribute("href").slice(1);
  if (!panelMap.has(id)) return;
  event.preventDefault();
  showPanel(id);
});

window.addEventListener("popstate", () => {
  const id = location.hash.slice(1);
  showPanel(id, { updateHash: false, scroll: false });
});

const initialId = location.hash.slice(1);
showPanel(panelMap.has(initialId) ? initialId : panels[0].id, {
  updateHash: false,
  scroll: false,
});

/* Animated stat counters */
const statNumbers = document.querySelectorAll(".stat-number");

const countUp = (el) => {
  const target = Number(el.dataset.target);
  const suffix = el.dataset.suffix || "";
  const duration = 1200;
  const start = performance.now();

  const tick = (now) => {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(eased * target) + suffix;
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
};

const statsObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        countUp(entry.target);
        statsObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.6 }
);

statNumbers.forEach((el) => statsObserver.observe(el));

/* Back to top */
const backToTop = document.getElementById("backToTop");

window.addEventListener("scroll", () => {
  backToTop.classList.toggle("visible", window.scrollY > 500);
});

backToTop.addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
});
