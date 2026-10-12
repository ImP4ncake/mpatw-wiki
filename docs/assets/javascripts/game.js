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

  function init() {
    initAccent();
    initSearchBox();
    initCounters();
    initCountdowns();
    initRelativeTimes();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
