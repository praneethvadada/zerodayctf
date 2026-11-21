/* ZeroDayCTF live countdown.
 * Time comes from the server (/server-time), never from the visitor's clock:
 * we measure the offset between server and browser once, then tick locally and
 * re-sync every 30 seconds (and whenever the tab becomes visible again).
 */
(function () {
  "use strict";
  var offset = 0;          // server_now - browser_now, in ms
  var cfg = null;
  var ready = false;

  function now() { return Date.now() + offset; }

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function phase() {
    var t = now() / 1000;
    if (!cfg || !cfg.start || !cfg.end) return { key: "none", label: "Schedule coming soon", target: null };
    if (t < cfg.start) return { key: "before", label: "Event starts in", target: cfg.start };
    if (t < cfg.end) return { key: "solve", label: "Solving ends in", target: cfg.end };
    if (cfg.writeup_end && t < cfg.writeup_end) return { key: "writeup", label: "Writeup window ends in", target: cfg.writeup_end };
    return { key: "over", label: "Event has ended", target: null };
  }

  function cells(diff) {
    var s = Math.max(0, Math.floor(diff));
    return [
      ["Days", Math.floor(s / 86400)],
      ["Hours", Math.floor((s % 86400) / 3600)],
      ["Mins", Math.floor((s % 3600) / 60)],
      ["Secs", s % 60]
    ];
  }

  function bigHTML(p) {
    if (!p.target) {
      return '<div class="zd-timer-label">' + p.label + "</div>";
    }
    var diff = p.target - now() / 1000;
    var out = '<div class="zd-timer-label">' + p.label + '</div><div class="zd-timer-cells">';
    cells(diff).forEach(function (c) {
      out += '<div class="zd-timer-cell"><b>' + pad(c[1]) + "</b><span>" + c[0] + "</span></div>";
    });
    return out + "</div>";
  }

  function barHTML(p) {
    if (!p.target) return "<strong>" + p.label + "</strong>";
    var c = cells(p.target - now() / 1000);
    var link = "";
    if (p.key === "writeup" && window.init && window.init.userName) {
      link = " <a class=\"zd-bar-link\" href=\"/writeups\">Submit your writeup &rarr;</a>";
    }
    return "<strong>" + p.label + "</strong> <span class=\"zd-bar-time\">" +
      c[0][1] + "d " + pad(c[1][1]) + "h " + pad(c[2][1]) + "m " + pad(c[3][1]) + "s</span>" + link;
  }

  function render() {
    if (!ready) return;
    var p = phase();
    var bar = document.getElementById("zd-timebar");
    if (bar) {
      bar.hidden = false;
      bar.setAttribute("data-phase", p.key);
      bar.innerHTML = barHTML(p);
    }
    var slot = document.getElementById("zd-timer-slot");
    if (slot) {
      slot.setAttribute("data-phase", p.key);
      slot.innerHTML = bigHTML(p);
    }
  }

  function sync() {
    var t0 = Date.now();
    fetch("/server-time", { cache: "no-store", credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var t1 = Date.now();
        // assume the response was generated halfway through the round trip
        offset = d.now * 1000 + (t1 - t0) / 2 - t1;
        cfg = d;
        ready = true;
        render();
      })
      .catch(function () { /* keep ticking on the last known offset */ });
  }

  function start() {
    sync();
    setInterval(render, 1000);
    setInterval(sync, 30000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) sync();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
