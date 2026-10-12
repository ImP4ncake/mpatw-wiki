/* MPATW Wiki - small dynamic touches: counters, countdowns, "x hours ago". */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function compact(n) {
    var units = [[1e9, "B"], [1e6, "M"], [1e3, "K"]];
    for (var i = 0; i < units.length; i++) {
      if (n >= units[i][0]) {
        return (n / units[i][0]).toFixed(1).replace(/\.0$/, "") + units[i][1];
      }
    }
    return String(Math.round(n));
  }

  function format(el, value) {
    var decimals = parseInt(el.getAttribute("data-decimals") || "0", 10);
    var suffix = el.getAttribute("data-suffix") || "";
    if (el.hasAttribute("data-compact")) return compact(value) + suffix;
    return value.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    }) + suffix;
  }

  // Count-up animation for numbers, when they scroll into view.
  function countUp(el) {
    var target = parseFloat(el.getAttribute("data-count"));
    if (isNaN(target)) return;
    if (reduceMotion) {
      el.textContent = format(el, target);
      return;
    }
    var start = performance.now();
    var duration = 1200;
    function frame(now) {
      var t = Math.min((now - start) / duration, 1);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = format(el, target * eased);
      if (t < 1) requestAnimationFrame(frame);
      else el.textContent = format(el, target);
    }
    requestAnimationFrame(frame);
  }

  function initCounters() {
    var els = document.querySelectorAll("[data-count]");
    if (!("IntersectionObserver" in window)) {
      els.forEach(countUp);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          countUp(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.4 });
    els.forEach(function (el) { io.observe(el); });
  }

  // Countdowns in the in-game style: 20d 9h 23m 26s
  function initCountdowns() {
    var els = Array.prototype.slice.call(document.querySelectorAll("[data-countdown]"));
    var hiders = Array.prototype.slice.call(document.querySelectorAll("[data-hide-after]"));
    function tick() {
      var now = Date.now();
      els.forEach(function (el) {
        var end = Date.parse(el.getAttribute("data-countdown"));
        var left = Math.max(0, Math.floor((end - now) / 1000));
        if (!left) {
          el.textContent = "Ended";
          return;
        }
        var d = Math.floor(left / 86400);
        var h = Math.floor((left % 86400) / 3600);
        var m = Math.floor((left % 3600) / 60);
        var s = left % 60;
        el.textContent = (d ? d + "d " : "") + h + "h " + m + "m " + s + "s";
      });
      hiders.forEach(function (el) {
        if (Date.parse(el.getAttribute("data-hide-after")) <= now) el.hidden = true;
      });
    }
    tick();
    if (els.length) setInterval(tick, 1000);
  }

  // "3 hours ago" next to update times
  function initRelativeTimes() {
    var rtf = window.Intl && Intl.RelativeTimeFormat ? new Intl.RelativeTimeFormat("en", { numeric: "auto" }) : null;
    if (!rtf) return;
    document.querySelectorAll("[data-time]").forEach(function (el) {
      var then = Date.parse(el.getAttribute("data-time"));
      if (isNaN(then)) return;
      var seconds = Math.round((then - Date.now()) / 1000);
      var abs = Math.abs(seconds);
      var text;
      if (abs < 3600) text = rtf.format(Math.round(seconds / 60), "minute");
      else if (abs < 86400) text = rtf.format(Math.round(seconds / 3600), "hour");
      else if (abs < 86400 * 45) text = rtf.format(Math.round(seconds / 86400), "day");
      else return;
      el.setAttribute("title", el.textContent);
      el.textContent = text;
    });
  }

  // Each wiki category has its own color: set it from the URL.
  var ACCENTS = {
    "game-info": "blue", mechanics: "violet", badges: "gold", activities: "green", items: "pink",
    servers: "cyan", events: "orange", community: "red", guides: "teal", wiki: "indigo"
  };

  function initAccent() {
    var parts = location.pathname.split("/").filter(Boolean);
    for (var i = 0; i < parts.length; i++) {
      if (ACCENTS[parts[i]]) {
        document.body.setAttribute("data-accent", ACCENTS[parts[i]]);
        return;
      }
    }
  }

  // The big search box on the home page opens the site search.
  function initSearchBox() {
    document.querySelectorAll("[data-open-search]").forEach(function (el) {
      el.addEventListener("click", function (event) {
        var button = document.querySelector(".md-search__button");
        var toggle = document.getElementById("__search");
        event.preventDefault();
        if (button && button.offsetParent !== null) {
          button.click();
        } else if (toggle) {
          toggle.checked = true;
          toggle.dispatchEvent(new Event("change"));
        }
        setTimeout(function () {
          var input = document.querySelector(".md-search__input, .md-search input");
          if (input) input.focus();
        }, 80);
      });
    });
  }


  // ---------------------------------------------------------------------
  // Motion
  // ---------------------------------------------------------------------

  // Blocks slide in and grids pop in tile by tile as you scroll.
  var BLOCKS = ".md-typeset h2, .md-typeset .md-typeset__scrollwrap, .md-typeset .admonition, .md-typeset details, " +
    ".mp-menu, .mp-chat, .mp-cta, .mp-event, .mp-soon, .mp-gamemenu, .mp-mainmenu, .mp-chart, .mp-chart-empty, .mp-missing, .mp-item, .mp-patch";
  var GRIDS = ".mp-cats, .mp-cards, .mp-featured, .mp-badges, .mp-titles, .mp-tags, .mp-passes, .mp-timeline, " +
    ".mp-hunt, .mp-platforms, .mp-stats--grid";

  function initReveal() {
    if (!("IntersectionObserver" in window)) return;
    var targets = [];
    document.querySelectorAll(BLOCKS).forEach(function (el) {
      if (el.closest(".mp-hero")) return;
      el.classList.add("mp-reveal");
      targets.push(el);
    });
    document.querySelectorAll(GRIDS).forEach(function (el) {
      if (el.closest(".mp-hero")) return;
      var kids = el.children.length === 1 && el.children[0].tagName === "P" ? el.children[0].children : el.children;
      Array.prototype.forEach.call(kids, function (kid, i) { kid.style.setProperty("--k", Math.min(i, 14)); });
      if (kids !== el.children) el.children[0].classList.add("mp-reveal-kids");
      el.classList.add("mp-reveal-kids");
      targets.push(el);
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          entry.target.querySelectorAll(".mp-reveal-kids").forEach(function (k) { k.classList.add("is-in"); });
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
    targets.forEach(function (el) { io.observe(el); });
  }

  // Cards lean towards the mouse, with a light reflection.
  function initTilt() {
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    var selector = "a.mp-cat, a.mp-card, .mp-badge, .mp-pass, a.mp-title-card, a.mp-tag-card, a.mp-feature, .mp-platform";
    document.querySelectorAll(selector).forEach(function (el) {
      el.classList.add("mp-tilt");
      el.addEventListener("pointermove", function (event) {
        var r = el.getBoundingClientRect();
        var x = (event.clientX - r.left) / r.width;
        var y = (event.clientY - r.top) / r.height;
        el.style.setProperty("--ry", ((x - 0.5) * 14).toFixed(2) + "deg");
        el.style.setProperty("--rx", ((0.5 - y) * 12).toFixed(2) + "deg");
        el.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
        el.style.setProperty("--my", (y * 100).toFixed(1) + "%");
        el.classList.add("is-tilting");
      });
      el.addEventListener("pointerleave", function () {
        el.classList.remove("is-tilting");
      });
    });
  }

  // Clouds and the globe follow the mouse a little.
  function initParallax() {
    var hero = document.querySelector(".mp-hero");
    if (!hero || !window.matchMedia("(hover: hover)").matches) return;
    hero.addEventListener("pointermove", function (event) {
      var r = hero.getBoundingClientRect();
      hero.style.setProperty("--px", (((event.clientX - r.left) / r.width) - 0.5).toFixed(3));
      hero.style.setProperty("--py", (((event.clientY - r.top) / r.height) - 0.5).toFixed(3));
    });
    hero.addEventListener("pointerleave", function () {
      hero.style.setProperty("--px", 0);
      hero.style.setProperty("--py", 0);
    });
  }

  // Chat bubbles saying hello in many languages float up in the sky.
  var HELLOS = ["Hi!", "Ciao!", "Hola!", "Bonjour!", "Hallo!", "Olá!", "Merhaba!", "Hej!", "Salut!", "Namaste!",
    "Konnichiwa!", "Annyeong!", "Privet!", "Halo!", "Kumusta!", "Sawasdee!", "Xin chào!", "Marhaba!", "Ahoj!",
    "Cześć!", "Szia!", "Jambo!", "Ni hao!", "Yassou!", "Hoi!", "Moi!", "Selam!", "Aloha!"];

  function initBubbles() {
    var sky = document.querySelector(".mp-hero__sky");
    var hero = document.querySelector(".mp-hero");
    var text = document.querySelector(".mp-hero__text");
    if (!sky || !hero || !text) return;
    var last = -1;
    var lanes = [];
    var busyUntil = [];

    // Bubbles only use the free sky to the right of the text, in separate
    // lanes, so they never cover the text or each other.
    function layout() {
      var heroBox = hero.getBoundingClientRect();
      var right = 0;
      Array.prototype.forEach.call(text.children, function (child) {
        var r = child.getBoundingClientRect();
        if (r.width) right = Math.max(right, r.right - heroBox.left);
      });
      var start = right + 30;
      var end = heroBox.width - 110;
      lanes = [];
      for (var x = start; x <= end; x += 120) lanes.push(x);
      busyUntil = lanes.map(function () { return 0; });
    }

    function spawn() {
      if (document.hidden || !lanes.length) return;
      var now = Date.now();
      var free = [];
      lanes.forEach(function (x, i) { if (busyUntil[i] <= now) free.push(i); });
      if (!free.length) return;
      var lane = free[Math.floor(Math.random() * free.length)];
      var i;
      do { i = Math.floor(Math.random() * HELLOS.length); } while (i === last);
      last = i;
      var duration = 8 + Math.random() * 3;
      busyUntil[lane] = now + duration * 450;
      var b = document.createElement("span");
      b.className = "mp-bubble";
      b.textContent = HELLOS[i];
      b.style.left = lanes[lane] + "px";
      b.style.setProperty("--d", duration.toFixed(1) + "s");
      b.style.setProperty("--sway", (Math.random() * 30 - 15).toFixed(0) + "px");
      b.addEventListener("animationend", function () { b.remove(); });
      sky.appendChild(b);
    }

    layout();
    window.addEventListener("resize", layout);
    for (var n = 0; n < 3; n++) setTimeout(spawn, 300 + n * 600);
    setInterval(spawn, 1300);
  }

  // Page titles and the wiki's name in the header get a black outline layer
  // under a gold layer, like the game's title, without letters cutting into
  // each other.
  function initTitles() {
    document.querySelectorAll(".md-typeset h1, .md-header__topic:first-child .md-ellipsis").forEach(function (h) {
      var copy = h.cloneNode(true);
      copy.querySelectorAll(".headerlink").forEach(function (x) { x.remove(); });
      var label = copy.textContent.trim();
      if (!label) return;
      h.setAttribute("data-text", label);
      h.classList.add("mp-outlined");
    });
  }

  // The name plate in the header leads to the home page, like the globe.
  function initHeaderName() {
    var logo = document.querySelector(".md-header__button.md-logo");
    var name = document.querySelector(".md-header__topic:first-child");
    if (!logo || !name) return;
    name.addEventListener("click", function () { window.location.href = logo.href; });
  }

  // Codes: click to copy, and the button says "Copied!" for a moment.
  function initCopyButtons() {
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      var label = btn.querySelector(".mp-code__btn");
      var timer;
      function copied() {
        btn.classList.add("is-copied");
        if (label) label.textContent = "Copied!";
        clearTimeout(timer);
        timer = setTimeout(function () {
          btn.classList.remove("is-copied");
          if (label) label.textContent = "Copy";
        }, 1600);
      }
      function fallback(text) {
        var area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        try {
          if (document.execCommand("copy")) copied();
        } catch (e) { /* the code stays visible to copy by hand */ }
        area.remove();
      }
      btn.addEventListener("click", function () {
        var text = btn.getAttribute("data-copy");
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(copied, function () { fallback(text); });
        } else {
          fallback(text);
        }
      });
    });
  }

  // Every page below the home page gets a "back" button to the section it
  // belongs to (taken from the breadcrumb trail), so you don't have to go all
  // the way back home. On a section page it leads home.
  function initBackButton() {
    var links = document.querySelectorAll(".md-path .md-path__link");
    var title = document.querySelector(".md-content__inner h1");
    if (!links.length || !title) return;
    var here = location.href.split("#")[0].replace(/index\.html$/, "");
    var target = null;
    for (var i = links.length - 1; i >= 0; i--) {
      if (links[i].href.split("#")[0].replace(/index\.html$/, "") !== here) {
        target = links[i];
        break;
      }
    }
    if (!target) return;
    var name = target.textContent.trim();
    var back = document.createElement("a");
    back.className = "mp-btn mp-btn--back";
    back.href = target.href;
    back.setAttribute("aria-label", "Back to " + name);
    back.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 19-7-7 7-7M19 12H5"/></svg>' +
      "<span></span>";
    back.querySelector("span").textContent = name;
    title.parentNode.insertBefore(back, title);
    document.body.classList.add("mp-has-back");
  }

  // A round "back to top" button that shows up once you scroll down.
  // It scrolls smoothly back up, without reloading the page.
  function initBackToTop() {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "mp-totop";
    btn.title = "Back to top";
    btn.setAttribute("aria-label", "Back to top");
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 7-7 7 7M12 19V5"/></svg>';
    document.body.appendChild(btn);

    var shown = false;
    var ticking = false;
    function update() {
      var show = window.scrollY > 600;
      if (show !== shown) {
        shown = show;
        btn.classList.toggle("is-shown", show);
      }
      ticking = false;
    }
    window.addEventListener("scroll", function () {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
    }, { passive: true });
    update();

    btn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
    });
  }

  // A burst of sparks when you press Play.
  function initSparks() {
    var EMOJI = ["✨", "⭐", "🌍", "💬", "🎉"];
    document.querySelectorAll(".mp-btn--green").forEach(function (btn) {
      btn.addEventListener("click", function (event) {
        for (var i = 0; i < 12; i++) {
          var s = document.createElement("span");
          s.className = "mp-spark";
          s.textContent = EMOJI[i % EMOJI.length];
          var angle = (Math.PI * 2 * i) / 12;
          var dist = 50 + Math.random() * 50;
          s.style.left = event.clientX + "px";
          s.style.top = event.clientY + "px";
          s.style.setProperty("--sx", (Math.cos(angle) * dist).toFixed(0) + "px");
          s.style.setProperty("--sy", (Math.sin(angle) * dist).toFixed(0) + "px");
          s.addEventListener("animationend", function () { this.remove(); });
          document.body.appendChild(s);
        }
      });
    });
  }

  function initMotion() {
    if (reduceMotion) return;
    initReveal();
    initTilt();
    initParallax();
    initBubbles();
    initSparks();
  }

  function init() {
    initTitles();
    initHeaderName();
    initCopyButtons();
    initBackToTop();
    initBackButton();
    initAccent();
    initSearchBox();
    initCounters();
    initCountdowns();
    initRelativeTimes();
    initMotion();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
