/* MPATW Wiki - the Rules page as an open book.
   One chapter at a time on the right page, with a page-turn animation,
   rules that open smoothly, search by code or word, a picture viewer
   and links like #c1 that open a rule directly. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var SVG = {
    x: '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    left: '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>',
    right: '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>'
  };

  function init() {
    var rb = document.querySelector(".rb");
    if (!rb) return;
    rb.classList.add("has-js");
    rb.querySelectorAll(".mp-reveal, .mp-reveal-kids").forEach(function (el) {
      el.classList.remove("mp-reveal", "mp-reveal-kids", "is-in");
    });

    var pagesBox = rb.querySelector(".rb-pages");
    var chapters = Array.prototype.slice.call(rb.querySelectorAll(".rb-ch:not(.rb-ch--results)"));
    var results = rb.querySelector("#rb-results");
    var indexLinks = Array.prototype.slice.call(rb.querySelectorAll(".rb-ix"));
    var indexBox = rb.querySelector(".rb-index__inner");
    var current = null;
    var lastChapter = chapters[0];
    var turning = null;

    function header() {
      var h = document.querySelector(".md-header");
      return h ? h.getBoundingClientRect().height : 56;
    }

    function setTop() {
      rb.style.setProperty("--rb-top", header() + "px");
    }
    setTop();
    window.addEventListener("resize", setTop);

    function isPhone() {
      return window.matchMedia("(max-width: 59.9375em)").matches;
    }

    function stickyOffset() {
      var off = header() + 12;
      if (isPhone()) {
        var ix = rb.querySelector(".rb-index");
        if (ix) off += ix.offsetHeight;
      }
      return off;
    }

    function scrollToY(y, smooth) {
      window.scrollTo({ top: Math.max(0, y), behavior: smooth && !reduceMotion ? "smooth" : "auto" });
    }

    function scrollToEl(el, smooth) {
      scrollToY(el.getBoundingClientRect().top + window.scrollY - stickyOffset() - 8, smooth);
    }

    function bookTopIfNeeded(smooth) {
      var top = pagesBox.getBoundingClientRect().top;
      var want = stickyOffset();
      if (top < want - 4 || top > window.innerHeight * 0.6) {
        scrollToY(top + window.scrollY - want, smooth);
      }
    }

    // ---------------------------------------------------------------- index highlight
    function markIndex(id) {
      indexLinks.forEach(function (a) {
        var on = a.getAttribute("data-ch") === id;
        a.classList.toggle("is-active", on);
        if (on) {
          a.setAttribute("aria-current", "page");
          if (isPhone() && indexBox) {
            var left = a.offsetLeft - indexBox.clientWidth / 2 + a.offsetWidth / 2;
            indexBox.scrollTo({ left: left, behavior: reduceMotion ? "auto" : "smooth" });
          }
        } else {
          a.removeAttribute("aria-current");
        }
      });
    }

    // ---------------------------------------------------------------- page turn
    function finishTurn() {
      if (!turning) return;
      turning.anims.forEach(function (a) { a.cancel(); });
      turning.els.forEach(function (el) {
        el.classList.remove("is-leaving", "is-arriving", "is-top");
      });
      pagesBox.classList.remove("is-flipping");
      pagesBox.style.minHeight = "";
      turning = null;
    }

    function show(target, opts) {
      opts = opts || {};
      if (!target || target === current) {
        if (target && opts.scroll) bookTopIfNeeded(true);
        return;
      }
      finishTurn();
      var from = current;
      var fromHeight = from ? from.offsetHeight : 0;
      var all = chapters.concat([results]);
      var forward = !from || all.indexOf(target) >= all.indexOf(from);
      current = target;
      if (target !== results) lastChapter = target;
      target.hidden = false;

      all.forEach(function (c) {
        c.classList.toggle("is-current", c === target);
      });
      markIndex(target === results ? "" : target.id);

      if (from && opts.animate !== false && !reduceMotion) {
        var dur = 620;
        var ease = forward ? "cubic-bezier(0.5, 0.05, 0.6, 0.95)" : "cubic-bezier(0.3, 0.4, 0.4, 1)";
        pagesBox.classList.add("is-flipping");
        pagesBox.style.minHeight = Math.min(fromHeight, window.innerHeight * 1.2) + "px";
        from.classList.add("is-leaving");
        target.classList.add("is-arriving");
        var anims = [];
        if (forward) {
          // the old page lifts from its right edge and turns over the spine
          from.classList.add("is-top");
          anims.push(from.animate(
            [{ transform: "rotateY(0deg)" }, { transform: "rotateY(-96deg)" }],
            { duration: dur, easing: ease, fill: "forwards" }
          ));
          anims.push(target.animate(
            [{ transform: "translateX(-10px) scale(0.985)", opacity: 0.75 }, { transform: "none", opacity: 1 }],
            { duration: dur, easing: "ease-out" }
          ));
        } else {
          // going back, the previous page turns back over from the spine
          target.classList.add("is-top");
          anims.push(target.animate(
            [{ transform: "rotateY(-96deg)" }, { transform: "rotateY(0deg)" }],
            { duration: dur, easing: ease }
          ));
          anims.push(from.animate(
            [{ opacity: 1, transform: "none" }, { opacity: 0.6, transform: "translateX(10px) scale(0.985)" }],
            { duration: dur, easing: "ease-in", fill: "forwards" }
          ));
        }
        turning = { anims: anims, els: [from, target] };
        anims[0].onfinish = function () {
          finishTurn();
        };
      }

      if (opts.hash !== false && target !== results) {
        var hash = "#" + target.id;
        if (location.hash !== hash) {
          if (opts.push) history.pushState({ rb: target.id }, "", hash);
          else history.replaceState({ rb: target.id }, "", hash);
        }
      }
      if (opts.scroll) bookTopIfNeeded(true);
    }

    function chapterOf(el) {
      return el && el.closest(".rb-ch:not(.rb-ch--results)");
    }

    // ---------------------------------------------------------------- opening rules
    function animateDetails(d, open) {
      var body = d.querySelector(".rb-rule__body");
      if (d._anim) {
        d._anim.cancel();
        d._anim = null;
      }
      d._closing = !open;
      if (!body || reduceMotion) {
        d.open = open;
        d._closing = false;
        return;
      }
      if (open) {
        d.open = true;
        var h = body.offsetHeight;
        d._anim = body.animate(
          [{ height: "0px", opacity: 0 }, { height: h + "px", opacity: 1 }],
          { duration: 420, easing: "cubic-bezier(0.25, 1, 0.4, 1)" }
        );
        d._anim.onfinish = function () { d._anim = null; };
        var inner = body.firstElementChild;
        if (inner) {
          Array.prototype.forEach.call(inner.children, function (child, i) {
            child.animate(
              [{ opacity: 0, transform: "translateY(10px)" }, { opacity: 1, transform: "none" }],
              { duration: 360, delay: 60 + Math.min(i, 8) * 55, easing: "ease-out", fill: "backwards" }
            );
          });
        }
      } else {
        var from = body.offsetHeight;
        d._anim = body.animate(
          [{ height: from + "px", opacity: 1 }, { height: "0px", opacity: 0 }],
          { duration: 260, easing: "ease-in" }
        );
        d._anim.onfinish = function () {
          d.open = false;
          d._anim = null;
          d._closing = false;
        };
      }
    }

    rb.addEventListener("click", function (event) {
      var summary = event.target.closest("details.rb-rule > summary, details.rb-faq > summary");
      if (!summary || !rb.contains(summary)) return;
      event.preventDefault();
      var d = summary.parentElement;
      var open = !d.open || !!d._closing;
      animateDetails(d, open);
      if (open && d.classList.contains("rb-rule") && d.id) {
        history.replaceState(history.state, "", "#" + d.id);
      }
    });

    function openRule(el, opts) {
      opts = opts || {};
      var ch = chapterOf(el);
      if (ch) show(ch, { animate: opts.animate, push: opts.push, hash: false });
      if (el.tagName === "DETAILS") {
        el.open = true;
        el.classList.remove("is-flash");
        void el.offsetWidth;
        el.classList.add("is-flash");
      }
      if (el.id && opts.hash !== false) {
        var hash = "#" + el.id;
        if (location.hash !== hash) history[opts.push ? "pushState" : "replaceState"]({ rb: el.id }, "", hash);
      }
      setTimeout(function () { scrollToEl(el, true); }, opts.animate === false ? 30 : 140);
    }

    // ---------------------------------------------------------------- links inside the book
    rb.addEventListener("click", function (event) {
      var a = event.target.closest("a[href^='#']");
      if (!a || !rb.contains(a)) return;
      var id = decodeURIComponent(a.getAttribute("href").slice(1));
      var el = id && document.getElementById(id);
      if (!el || !rb.contains(el)) return;
      event.preventDefault();
      if (searchInput && searchInput.value) {
        searchInput.value = "";
        rb.classList.remove("is-searching");
      }
      if (el.classList.contains("rb-ch")) {
        show(el, { push: true, scroll: true });
      } else {
        openRule(el, { push: true });
      }
    });

    // copy a link to one rule
    rb.addEventListener("click", function (event) {
      var btn = event.target.closest(".rb-copy");
      if (!btn) return;
      var url = location.href.split("#")[0] + "#" + btn.getAttribute("data-code");
      var label = btn.querySelector("span");
      function done() {
        btn.classList.add("is-done");
        if (label) label.textContent = "Link copied!";
        setTimeout(function () {
          btn.classList.remove("is-done");
          if (label) label.textContent = "Copy link";
        }, 1800);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done, function () { history.replaceState(null, "", url); done(); });
      } else {
        history.replaceState(null, "", url);
        done();
      }
    });

    // keyboard: arrows turn the page, / jumps to the search box
    document.addEventListener("keydown", function (event) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      var tag = (event.target.tagName || "").toLowerCase();
      var typing = tag === "input" || tag === "textarea" || event.target.isContentEditable;
      if (lightbox && !lightbox.hidden) return;
      if (event.key === "/" && !typing && searchInput) {
        event.preventDefault();
        searchInput.focus();
        return;
      }
      if (typing || !current || current === results) return;
      var i = chapters.indexOf(current);
      if (event.key === "ArrowRight" && i < chapters.length - 1) show(chapters[i + 1], { push: true, scroll: true });
      if (event.key === "ArrowLeft" && i > 0) show(chapters[i - 1], { push: true, scroll: true });
    });

    // ---------------------------------------------------------------- search
    var searchInput = rb.querySelector(".rb-search input");
    var resultsList = results && results.querySelector(".rb-results");
    var resultsCount = results && results.querySelector(".rb-results__count");
    var entries = [];
    rb.querySelectorAll("details.rb-rule").forEach(function (d) {
      var ch = chapterOf(d);
      entries.push({
        el: d,
        code: d.id.toLowerCase(),
        title: d.querySelector(".rb-rule__title").textContent,
        where: ch ? ch.getAttribute("data-title") : "",
        text: (d.getAttribute("data-search") || "") + " " + d.textContent.toLowerCase(),
        badge: d.querySelector(".rb-code").outerHTML,
        plain: plainText(d),
        cls: d.className.match(/rb-rule--\w/) ? d.className.match(/rb-rule--\w/)[0] : ""
      });
    });
    rb.querySelectorAll("details.rb-faq").forEach(function (d) {
      entries.push({
        el: d,
        code: "",
        title: d.querySelector(".rb-faq__t").textContent,
        where: "Questions",
        text: (d.getAttribute("data-search") || "") + " " + d.textContent.toLowerCase(),
        badge: '<span class="rb-faq__q">?</span>',
        plain: plainText(d),
        cls: ""
      });
    });

    function escapeHtml(s) {
      return s.replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }

    function highlight(text, q) {
      var safe = escapeHtml(text);
      if (!q || q.length < 2) return safe;
      var re = new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
      return safe.replace(re, "<mark>$1</mark>");
    }

    function plainText(d) {
      return Array.prototype.map.call(
        d.querySelectorAll(".rb-callout, .rb-explain p:not(.rb-explain__head), .rb-ex__t, .rb-ex__d, .rb-count, .rb-related p, .rb-faq__a"),
        function (e) { return e.textContent.trim(); }
      ).join(" · ").replace(/\s+/g, " ");
    }

    function snippet(entry, q) {
      if (!q || q.length < 2) return "";
      var full = entry.plain;
      var i = full.toLowerCase().indexOf(q);
      if (i === -1) return "";
      var start = Math.max(0, i - 40);
      if (start) start = full.indexOf(" ", start) + 1 || start;
      var end = Math.min(full.length, i + q.length + 70);
      var cut = full.lastIndexOf(" ", end);
      if (end < full.length && cut > i + q.length) end = cut;
      return (start ? "…" : "") + full.slice(start, end).trim() + (end < full.length ? "…" : "");
    }

    function runSearch() {
      var q = (searchInput.value || "").trim().toLowerCase();
      if (!q) {
        rb.classList.remove("is-searching");
        if (current === results) show(lastChapter, { animate: false });
        return;
      }
      rb.classList.add("is-searching");
      var hits = entries.filter(function (e) {
        return e.code === q || e.text.indexOf(q) !== -1;
      });
      hits.sort(function (a, b) {
        var sa = a.code === q ? 0 : a.title.toLowerCase().indexOf(q) !== -1 ? 1 : 2;
        var sb = b.code === q ? 0 : b.title.toLowerCase().indexOf(q) !== -1 ? 1 : 2;
        return sa - sb;
      });
      resultsCount.textContent = hits.length
        ? hits.length + (hits.length === 1 ? " rule or answer matches" : " rules and answers match") + " “" + searchInput.value.trim() + "”"
        : "Nothing matches “" + searchInput.value.trim() + "”";
      resultsList.innerHTML = hits.length
        ? hits.map(function (e, i) {
          var snip = snippet(e, q);
          return '<a class="rb-hit ' + e.cls + '" href="#' + (e.el.id || "") + '" data-i="' + entries.indexOf(e) + '" style="--k:' + Math.min(i, 12) + '">' +
            e.badge + '<span class="rb-hit__t"><b>' + highlight(e.title, q) + "</b><small>" +
            escapeHtml(e.where) + (snip ? " · " + highlight(snip, q) : "") + "</small></span></a>";
        }).join("")
        : '<p class="rb-empty">No rule uses these words. Try a ban code like <b>a4</b>, or a word like <b>avatar</b>, <b>mod</b> or <b>unban</b>.</p>';
      show(results, { animate: current !== results, hash: false });
    }

    if (searchInput) {
      searchInput.addEventListener("input", runSearch);
      searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          searchInput.value = "";
          runSearch();
        }
        if (event.key === "Enter") {
          event.preventDefault();
          var first = resultsList && resultsList.querySelector(".rb-hit");
          if (first) first.click();
        }
      });
    }

    if (resultsList) {
      resultsList.addEventListener("click", function (event) {
        var a = event.target.closest(".rb-hit");
        if (!a) return;
        event.preventDefault();
        event.stopPropagation();
        var entry = entries[+a.getAttribute("data-i")];
        searchInput.value = "";
        rb.classList.remove("is-searching");
        openRule(entry.el, { push: true, hash: !!entry.el.id });
      });
    }

    // ---------------------------------------------------------------- pictures
    var lightbox = null;
    var lbList = [];
    var lbIndex = 0;
    var lbReturn = null;

    function buildLightbox() {
      lightbox = document.createElement("div");
      lightbox.className = "rb-lb";
      lightbox.hidden = true;
      lightbox.setAttribute("role", "dialog");
      lightbox.setAttribute("aria-modal", "true");
      lightbox.setAttribute("aria-label", "Example picture");
      lightbox.innerHTML =
        '<figure><img alt=""><figcaption><span class="rb-lb__mark"></span><span class="rb-lb__cap"></span>' +
        '<span class="rb-lb__count"></span></figcaption></figure>' +
        '<button type="button" class="rb-lb__close" aria-label="Close">' + SVG.x + "</button>" +
        '<button type="button" class="rb-lb__prev" aria-label="Previous picture">' + SVG.left + "</button>" +
        '<button type="button" class="rb-lb__next" aria-label="Next picture">' + SVG.right + "</button>";
      document.body.appendChild(lightbox);
      lightbox.addEventListener("click", function (event) {
        if (event.target.closest(".rb-lb__close") || event.target === lightbox) closeLightbox();
        else if (event.target.closest(".rb-lb__prev")) showPic(lbIndex - 1);
        else if (event.target.closest(".rb-lb__next")) showPic(lbIndex + 1);
      });
      document.addEventListener("keydown", function (event) {
        if (lightbox.hidden) return;
        if (event.key === "Escape") closeLightbox();
        if (event.key === "ArrowLeft") showPic(lbIndex - 1);
        if (event.key === "ArrowRight") showPic(lbIndex + 1);
      });
      var startX = null;
      lightbox.addEventListener("touchstart", function (e) { startX = e.touches[0].clientX; }, { passive: true });
      lightbox.addEventListener("touchend", function (e) {
        if (startX === null) return;
        var dx = e.changedTouches[0].clientX - startX;
        if (Math.abs(dx) > 50) showPic(lbIndex + (dx < 0 ? 1 : -1));
        startX = null;
      });
    }

    function showPic(i) {
      if (i < 0 || i >= lbList.length) return;
      lbIndex = i;
      var pic = lbList[i];
      var img = lightbox.querySelector("img");
      var ok = pic.getAttribute("data-mark") === "ok";
      img.src = pic.querySelector("img").currentSrc || pic.querySelector("img").src;
      img.alt = pic.getAttribute("data-cap");
      var mark = lightbox.querySelector(".rb-lb__mark");
      mark.className = "rb-lb__mark" + (ok ? " rb-lb__mark--ok" : "");
      mark.textContent = (ok ? "✓ Not bannable" : "✕ Bannable") + " · " + pic.getAttribute("data-rule");
      lightbox.querySelector(".rb-lb__cap").textContent = pic.getAttribute("data-cap");
      lightbox.querySelector(".rb-lb__count").textContent = lbList.length > 1 ? i + 1 + " / " + lbList.length : "";
      lightbox.querySelector(".rb-lb__prev").hidden = i === 0;
      lightbox.querySelector(".rb-lb__next").hidden = i === lbList.length - 1;
      pic.classList.add("is-shown");
      if (!reduceMotion) {
        img.animate([{ opacity: 0, transform: "scale(0.97)" }, { opacity: 1, transform: "none" }], { duration: 220, easing: "ease-out" });
      }
    }

    function openLightbox(pic) {
      if (!lightbox) buildLightbox();
      var rule = pic.closest(".rb-rule");
      lbList = Array.prototype.slice.call((rule || rb).querySelectorAll(".rb-pic"));
      lbReturn = pic;
      lightbox.hidden = false;
      document.documentElement.style.overflow = "hidden";
      showPic(lbList.indexOf(pic));
      requestAnimationFrame(function () { lightbox.classList.add("is-open"); });
      lightbox.querySelector(".rb-lb__close").focus();
    }

    function closeLightbox() {
      lightbox.classList.remove("is-open");
      document.documentElement.style.overflow = "";
      setTimeout(function () {
        lightbox.hidden = true;
        if (lbReturn) lbReturn.focus();
      }, reduceMotion ? 0 : 220);
    }

    rb.addEventListener("click", function (event) {
      var pic = event.target.closest(".rb-pic");
      if (!pic) return;
      event.preventDefault();
      if (pic.classList.contains("is-spoiler") && !pic.classList.contains("is-shown")) {
        pic.classList.add("is-shown");
        return;
      }
      openLightbox(pic);
    });

    // ---------------------------------------------------------------- start: which page to open
    function fromHash(push) {
      var id = decodeURIComponent((location.hash || "").slice(1));
      if (["rb-contents", "rb-read", "rb-lengths", "rulebook"].indexOf(id) !== -1) id = chapters[0].id;
      var el = id && document.getElementById(id);
      if (el && rb.contains(el) && el !== results) {
        if (el.classList.contains("rb-ch")) {
          show(el, { animate: !!current, hash: false, scroll: !!current });
        } else {
          openRule(el, { animate: !!current, hash: false, push: push });
        }
        return true;
      }
      return false;
    }

    if (!fromHash()) {
      show(chapters[0], { animate: false, hash: false });
    } else if (current && location.hash === "#" + current.id) {
      // the browser jumps to the chapter by itself; keep it below the header
      setTimeout(function () { bookTopIfNeeded(false); }, 80);
    }
    // back and forward buttons, and links to #c1 from other parts of the page
    window.addEventListener("hashchange", function () {
      if (!fromHash()) show(chapters[0], { hash: false, scroll: true });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
