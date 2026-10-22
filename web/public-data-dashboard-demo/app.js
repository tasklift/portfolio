(function () {
  var D = window.DASHBOARD_DATA;
  var NS = "http://www.w3.org/2000/svg";
  var $ = function (s) { return document.querySelector(s); };
  document.title = D.title + " - 지역 통계 대시보드";
  $("h1").textContent = D.title;
  $("#source").textContent = "출처: " + D.source;
  Array.prototype.forEach.call(document.querySelectorAll(".chart-unit"), function (n) {
    n.textContent = D.unit ? "단위: " + D.unit + " (점·막대에 마우스를 올리면 값이 보입니다)" : "점·막대에 마우스를 올리면 값이 보입니다";
  });

  var regionSel = $("#region-select"), fromSel = $("#period-from"), toSel = $("#period-to");
  function opt(sel, v, t) {
    var o = document.createElement("option");
    o.value = v; o.textContent = t; sel.appendChild(o);
  }
  opt(regionSel, "all", "전체 지역");
  D.regions.forEach(function (r) { opt(regionSel, r, r); });
  D.periods.forEach(function (p) { opt(fromSel, p, p); opt(toSel, p, p); });

  function fmt(n) {
    n = Math.round(n * 100) / 100;
    return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  function reset() {
    regionSel.value = "all";
    fromSel.value = D.periods.length ? D.periods[0] : "";
    toSel.value = D.periods.length ? D.periods[D.periods.length - 1] : "";
  }
  reset();

  var sortKey = "period", sortDir = 1;
  var current = [];

  function inRange(p, from, to) { return p >= from && p <= to; }
  function el(name, attrs, text) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  function cmp(a, b) {
    var r;
    if (sortKey === "value") r = a.value - b.value;
    else r = a[sortKey] < b[sortKey] ? -1 : a[sortKey] > b[sortKey] ? 1 : 0;
    return r * sortDir;
  }
  function defaultCmp(a, b) {
    if (a.period !== b.period) return a.period < b.period ? -1 : 1;
    return a.region < b.region ? -1 : a.region > b.region ? 1 : 0;
  }

  function render() {
    var region = regionSel.value, from = fromSel.value, to = toSel.value;
    var empty = from > to;
    var inPeriod = empty ? [] : D.records.filter(function (r) { return inRange(r.period, from, to); });
    var rows = region === "all" ? inPeriod : inPeriod.filter(function (r) { return r.region === region; });
    $("#empty-msg").hidden = !empty;

    // cards
    var total = rows.reduce(function (s, r) { return s + r.value; }, 0);
    var latest = rows.filter(function (r) { return r.period === to; })
      .reduce(function (s, r) { return s + r.value; }, 0);
    var sums = Object.create(null);
    inPeriod.forEach(function (r) { sums[r.region] = (sums[r.region] || 0) + r.value; });
    var ranked = D.regions
      .map(function (r, i) { return { region: r, value: sums[r] || 0, i: i }; })
      .sort(function (a, b) { return b.value - a.value || a.i - b.i; });
    var unit = D.unit || "";
    function card(id, dv, text) {
      var c = $('[data-id="' + id + '"]');
      c.setAttribute("data-value", dv);
      c.querySelector(".card-value").textContent = text;
    }
    card("card-total", total, fmt(total) + unit);
    card("card-latest", latest, fmt(latest) + unit);
    if (inPeriod.length) card("card-top", ranked[0].region, ranked[0].region);
    else card("card-top", "", "-");

    // trend
    var svg = $("#trend-chart");
    svg.textContent = "";
    var periods = empty ? [] : D.periods.filter(function (p) { return inRange(p, from, to); });
    var pv = periods.map(function (p) {
      return rows.filter(function (r) { return r.period === p; })
        .reduce(function (s, r) { return s + r.value; }, 0);
    });
    var W = 640, H = 260, L = 56, R = 16, T = 16, B = 36;
    var max = Math.max.apply(null, pv.concat([0])) || 1;
    for (var g = 0; g <= 4; g++) {
      var y = T + (H - T - B) * (1 - g / 4);
      svg.appendChild(el("line", { "class": "grid", x1: L, x2: W - R, y1: y, y2: y }));
      svg.appendChild(el("text", { x: L - 6, y: y + 4, "text-anchor": "end" }, fmt(max * g / 4)));
    }
    var pts = pv.map(function (v, i) {
      var x = periods.length === 1 ? (L + W - R) / 2 : L + (W - L - R) * i / (periods.length - 1);
      return [x, T + (H - T - B) * (1 - v / max)];
    });
    if (pts.length) {
      svg.appendChild(el("path", { "class": "line", d: pts.map(function (p, i) {
        return (i ? "L " : "M ") + p[0].toFixed(1) + " " + p[1].toFixed(1);
      }).join(" ") }));
      var step = Math.ceil(pts.length / 8);
      pts.forEach(function (p, i) {
        svg.appendChild(el("circle", { "class": "point", cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: 4,
          "data-period": periods[i], "data-value": pv[i] }));
        svg.lastChild.appendChild(el("title", {}, periods[i] + ": " + fmt(pv[i]) + D.unit));
        if (i % step === 0) svg.appendChild(el("text", { x: p[0].toFixed(1), y: H - 14, "text-anchor": "middle" }, periods[i]));
      });
    } else {
      svg.appendChild(el("path", { "class": "line", d: "M " + L + " " + (H - B) }));
    }

    // rank
    var rs = $("#rank-chart");
    rs.textContent = "";
    var rmax = ranked.length ? Math.max(ranked[0].value, 0) || 1 : 1;
    if (empty) ranked = [];
    var rowH = 30;
    var RH = Math.max(80, ranked.length * rowH + 20);
    rs.setAttribute("viewBox", "0 0 640 " + RH);
    ranked.forEach(function (r, i) {
      var y = 10 + i * rowH, w = Math.max(0, (640 - 200) * Math.max(r.value, 0) / rmax);
      rs.appendChild(el("text", { x: 90, y: y + 17, "text-anchor": "end" }, r.region));
      rs.appendChild(el("rect", { "class": "bar", x: 100, y: y, width: w.toFixed(1), height: 22, rx: 3,
        "data-region": r.region, "data-value": r.value }));
      rs.lastChild.appendChild(el("title", {}, r.region + ": " + fmt(r.value) + D.unit));
      rs.appendChild(el("text", { x: 106 + w, y: y + 17 }, fmt(r.value)));
    });

    // table
    current = rows.slice().sort(function (a, b) {
      var r = cmp(a, b);
      return r !== 0 ? r : defaultCmp(a, b);
    });
    var tb = $("#data-table tbody");
    tb.textContent = "";
    current.forEach(function (r) {
      var tr = document.createElement("tr");
      [r.region, r.period, fmt(r.value)].forEach(function (t) {
        var td = document.createElement("td"); td.textContent = t; tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    $("#row-count").textContent = current.length + "건";
    Array.prototype.forEach.call(document.querySelectorAll("#data-table th[data-key]"), function (th) {
      if (th.getAttribute("data-key") === sortKey)
        th.setAttribute("aria-sort", sortDir === 1 ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
  }

  [regionSel, fromSel, toSel].forEach(function (s) { s.addEventListener("change", render); });
  $("#reset-filter").addEventListener("click", function () { reset(); render(); });

  Array.prototype.forEach.call(document.querySelectorAll("#data-table th[data-key]"), function (th) {
    function go() {
      var k = th.getAttribute("data-key");
      if (k === sortKey) sortDir = -sortDir;
      else { sortKey = k; sortDir = 1; }
      render();
    }
    th.addEventListener("click", go);
    th.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
    });
  });

  function csvCell(s) {
    s = String(s);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  $("#download-csv").addEventListener("click", function () {
    var lines = ["지역,기간,값"].concat(current.map(function (r) {
      return [csvCell(r.region), csvCell(r.period), r.value].join(",");
    }));
    var blob = new Blob(["﻿" + lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "filtered.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  });

  render();
})();
