/* MPATW Wiki - the Rules page as a book: chapters, opening rules, search. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function init() {
    var book = document.querySelector(".rb-book");
    if (!book) return;
    book.classList.add("has-js");

    // game.js animates many blocks by itself; inside the book the pages do it.
    book.querySelectorAll(".mp-reveal, .mp-reveal-kids").forEach(function (el) {
      el.classList.remove("mp-reveal", "mp-reveal-kids");
    });

    var bar = book.querySelector(".rb-bar");
    var tabs = Array.prototype.slice.call(book.querySelectorAll(".rb-tab"));
    var ink = book.querySelector(".rb-tabs__ink");
    var tabsBox = book.querySelector(".rb-tabs");
    var pages = Array.prototype.slice.call(book.querySelectorAll(".rb-page[data-chapter]"));

    // Sticky bar sits right under the site header.
    function setTop() {
      var header = document.querySelector(".md-header");
      var h = header ? header.getBoundingClientRect().height : 48;
      book.style.setProperty("--rb-top", h + 8 + "px");
    }
    setTop();
    window.addEventListener("resize", setTop);

    function barOffset() {
      var header = document.querySelector(".md-header");
      return (header ? header.getBoundingClientRect().height : 48) + (bar ? bar.offsetHeight : 0) + 24;
    }

    function scrollToEl(el) {
      var y = el.getBoundingClientRect().top + window.scrollY - barOffset();
      window.scrollTo({ top: y, behavior: reduceMotion ? "auto" : "smooth" });
    }

    // ------------------------------------------------------------------ rules open and close smoothly
    function animateDetails(d, open) {
      var body = d.querySelector(".rb-rule__body");
      if (d._anim) d._anim.cancel();
      if (!body || reduceMotion) {
        d.open = open;
        return;
      }
      if (open) {
        d.open = true;
        var h = body.offsetHeight;
        d._anim = body.animate(
          [{ height: "0px", opacity: 0, transform: "translateY(-6px)" }, { height: h + "px", opacity: 1, transform: "none" }],
          { duration: 380, easing: "cubic-bezier(0.25, 1, 0.4, 1)" }
        );
      } else {
        var from = body.offsetHeight;
        d._anim = body.animate(
          [{ height: from + "px", opacity: 1 }, { height: "0px", opacity: 0 }],
          { duration: 260, easing: "ease-in" }
        );
        d._anim.onfinish = function () { d.open = false; d._anim = null; };
      }
    }

    book.querySelectorAll("details.rb-rule > summary, details.rb-faq > summary").forEach(function (s) {
      s.addEventListener("click", function (event) {
        event.preventDefault();
        var d = s.parentElement;
        animateDetails(d, !d.open || !!(d._anim && d._anim.onfinish));
      });
    });

    // ------------------------------------------------------------------ open all / close all
    var toggle = book.querySelector(".rb-toggle-all");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var open = toggle.getAttribute("data-open") !== "1";
        book.querySelectorAll("details.rb-rule").forEach(function (d) {
          if (!d.classList.contains("is-hidden")) d.open = open;
        });
        toggle.setAttribute("data-open", open ? "1" : "0");
        toggle.querySelector("span").textContent = open ? "Close all" : "Open all";
      });
    }

    // ------------------------------------------------------------------ chapter tabs, ink and progress
    function moveInk(tab) {
      if (!ink || !tab) return;
      ink.style.width = tab.offsetWidth + "px";
      ink.style.transform = "translateX(" + tab.offsetLeft + "px)";
      var left = tab.offsetLeft - tabsBox.clientWidth / 2 + tab.offsetWidth / 2;
      tabsBox.scrollTo({ left: left, behavior: reduceMotion ? "auto" : "smooth" });
    }

    function setActive(id) {
      tabs.forEach(function (t) {
        var on = t.getAttribute("href") === "#" + id;
        t.classList.toggle("is-active", on);
        if (on) moveInk(t);
      });
    }

    tabs.forEach(function (t) {
      t.addEventListener("click", function (event) {
        var target = book.querySelector(t.getAttribute("href"));
        if (!target) return;
        event.preventDefault();
        history.replaceState(null, "", t.getAttribute("href"));
        scrollToEl(target);
      });
    });

    book.querySelectorAll(".rb-toc a, a.rb-open").forEach(function (a) {
      a.addEventListener("click", function (event) {
        var target = book.querySelector(a.getAttribute("href"));
        if (!target) return;
        event.preventDefault();
        var cover = a.closest(".rb-cover");
        if (cover && !reduceMotion) {
          cover.classList.add("is-opening");
          setTimeout(function () {
            scrollToEl(target);
            setTimeout(function () { cover.classList.remove("is-opening"); }, 900);
          }, 450);
        } else {
          scrollToEl(target);
        }
      });
    });

    var progress = book.querySelector(".rb-progress");
    var ticking = false;
    function onScroll() {
      ticking = false;
      var line = barOffset() + 10;
      var current = null;
      pages.forEach(function (p) {
        if (p.getBoundingClientRect().top <= line && !p.classList.contains("is-hidden")) current = p;
      });
      if (!current) {
        current = pages.filter(function (p) { return !p.classList.contains("is-hidden"); })[0];
      }
      if (current) setActive(current.id);
      if (progress) {
        var r = book.getBoundingClientRect();
        var total = r.height - window.innerHeight;
        var done = total > 0 ? Math.min(Math.max(-r.top / total, 0), 1) : 0;
        progress.style.setProperty("--rb-progress", done.toFixed(3));
      }
    }
    window.addEventListener("scroll", function () {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(onScroll);
      }
    }, { passive: true });
    window.addEventListener("resize", onScroll);
    onScroll();

    // ------------------------------------------------------------------ pages turn in as you scroll
    var allPages = Array.prototype.slice.call(book.querySelectorAll(".rb-page"));
    allPages.forEach(function (p) {
      p.querySelectorAll(".rb-rule, .rb-faq, .rb-word, .rb-step, .rb-okcard").forEach(function (el, i) {
        el.style.setProperty("--k", Math.min(i, 12));
      });
    });
    if ("IntersectionObserver" in window && !reduceMotion) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            io.unobserve(entry.target);
          }
        });
      }, { threshold: 0.04 });
      allPages.forEach(function (p) { io.observe(p); });
    } else {
      allPages.forEach(function (p) { p.classList.add("is-in"); });
    }

    // ------------------------------------------------------------------ search
    var input = book.querySelector(".rb-search input");
    var noResults = book.querySelector(".rb-noresults");
    var items = Array.prototype.slice.call(book.querySelectorAll(".rb-rule, .rb-faq"));

    function runSearch() {
      var q = (input.value || "").trim().toLowerCase();
      book.classList.toggle("is-searching", q.length > 0);
      var shown = 0;
      items.forEach(function (el) {
        var text = (el.getAttribute("data-search") || "") + " " + el.textContent.toLowerCase();
        var code = (el.id || "").toLowerCase();
        var hit = !q || code === q || text.indexOf(q) !== -1;
        el.classList.toggle("is-hidden", !hit);
        if (hit && q) shown++;
      });
      allPages.forEach(function (p) {
        var any = p.querySelector(".rb-rule:not(.is-hidden), .rb-faq:not(.is-hidden)");
        p.classList.toggle("is-hidden", !!q && !any);
        if (q) p.classList.add("is-in");
      });
      if (noResults) noResults.hidden = !(q && shown === 0);
      if (q && /^[a-e][0-9]$/.test(q)) {
        var exact = book.querySelector("#" + q);
        if (exact && exact.tagName === "DETAILS") exact.open = true;
      }
      onScroll();
    }
    if (input) {
      input.addEventListener("input", runSearch);
      input.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          input.value = "";
          runSearch();
        }
      });
    }

    // ------------------------------------------------------------------ links like #c1 open the rule
    function openFromHash() {
      var id = decodeURIComponent((location.hash || "").slice(1));
      if (!id) return;
      var el = document.getElementById(id);
      if (!el || !book.contains(el)) return;
      var page = el.closest(".rb-page");
      if (page) page.classList.add("is-in");
      if (el.tagName === "DETAILS") {
        el.open = true;
        el.classList.remove("is-flash");
        void el.offsetWidth;
        el.classList.add("is-flash");
      }
      setTimeout(function () { scrollToEl(el); }, 60);
    }
    window.addEventListener("hashchange", openFromHash);
    openFromHash();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
