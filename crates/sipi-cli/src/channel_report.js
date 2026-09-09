"use strict";

(() => {
  const data = JSON.parse(document.getElementById("channel-data").textContent);
  const colors = ["#20734f", "#b4395b", "#166a9b", "#a16910"];
  const names = {
    waveform: ["tx_waveform_v", "channel_output_v", "rx_input_v", "rx_output_v"],
    impulse: ["channel_impulse_v_per_v"],
  };
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const integer = (input, fallback, low, high) => {
    const value = input.valueAsNumber;
    return Number.isFinite(value) ? clamp(Math.round(value), low, high) : fallback;
  };
  const exact = value => Object.is(value, -0) ? "-0" : String(value);
  const svgNode = (name, attributes, text) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    return node;
  };

  for (const section of document.querySelectorAll("section[data-view]")) {
    const kind = section.dataset.view;
    const { time, columns } = data[kind];
    if (!time.length || columns.length !== names[kind].length ||
        columns.some(values => values.length !== time.length)) throw new Error("Invalid report data dimensions");
    const controls = Object.fromEntries(Array.from(section.querySelectorAll("[data-control]"), node => [node.dataset.control, node]));
    const status = section.querySelector(".range-status");
    const table = section.querySelector(".readout");
    section.append(table);
    const svg = section.querySelector("svg");
    const visible = columns.map(() => true);
    const unit = kind === "waveform" ? "V" : "V/V";
    let start = 0;
    let count = Number(controls.count.value);
    let cursor = 0;
    let geometry;
    let cursorLine;
    const readings = new Map();
    for (const name of ["sample_index", "time_s", ...names[kind]]) {
      const row = table.tBodies[0].insertRow();
      const heading = document.createElement("th");
      heading.scope = "row";
      heading.textContent = name;
      row.append(heading);
      const value = row.insertCell();
      value.dataset.value = name;
      readings.set(name, value);
    }
    const legend = section.querySelector(".legend");
    legend.replaceChildren();
    names[kind].forEach((name, index) => {
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.setAttribute("aria-label", name);
      checkbox.addEventListener("change", () => { visible[index] = checkbox.checked; draw(); });
      const swatch = document.createElement("i");
      swatch.style.background = colors[index];
      label.append(checkbox, swatch, document.createTextNode(name));
      legend.append(label);
    });

    function readCursor() {
      controls.cursor.value = String(cursor);
      readings.get("sample_index").textContent = String(cursor);
      readings.get("time_s").textContent = exact(time[cursor]);
      columns.forEach((values, index) => { readings.get(names[kind][index]).textContent = exact(values[cursor]); });
      if (cursorLine) {
        const x = geometry.x(time[cursor]);
        cursorLine.setAttribute("x1", String(x));
        cursorLine.setAttribute("x2", String(x));
      }
      section.dataset.cursorSample = String(cursor);
    }

    function draw() {
      const end = Math.min(time.length, start + count);
      const width = Math.max(280, section.querySelector(".plot").clientWidth);
      const left = 80, right = width - 20, top = 24, bottom = 250;
      const first = time[start], last = time[end - 1];
      let low = 0, high = 0;
      columns.forEach((values, index) => {
        if (visible[index]) for (let i = start; i < end; i++) {
          low = Math.min(low, values[i]); high = Math.max(high, values[i]);
        }
      });
      const span = Math.max(high - low, 1e-12);
      const x = value => first === last ? (left + right) / 2 : left + (value - first) / (last - first) * (right - left);
      const y = value => bottom - (value - low) / span * (bottom - top);
      geometry = { x, left, right };
      svg.replaceChildren(svgNode("title", {}, `${unit} versus time in ps, samples ${start} to ${end - 1}`));
      svg.setAttribute("viewBox", `0 0 ${width} 300`);
      svg.setAttribute("aria-label", `${unit} versus time in ps, samples ${start} to ${end - 1}`);
      for (let tick = 0; tick <= 4; tick++) {
        const fraction = tick / 4, yt = bottom - fraction * (bottom - top);
        svg.append(svgNode("path", { d: `M${left} ${yt}H${right}`, stroke: "#e1e8e4" }));
        svg.append(svgNode("text", { x: left - 10, y: yt + 4, "text-anchor": "end", fill: "#55625d", "font-size": 12 }, (low + fraction * span).toExponential(2)));
      }
      const ticks = width < 600 ? 2 : 4;
      for (let tick = 0; tick <= ticks; tick++) {
        const fraction = tick / ticks;
        svg.append(svgNode("text", { x: left + fraction * (right - left), y: 273,
          "text-anchor": tick === 0 ? "start" : tick === ticks ? "end" : "middle", fill: "#55625d", "font-size": 12 },
          ((first + fraction * (last - first)) * 1e12).toPrecision(5)));
      }
      svg.append(svgNode("text", { x: 8, y: 15, "font-size": 12 }, unit));
      svg.append(svgNode("text", { x: (left + right) / 2, y: 295, "text-anchor": "middle", "font-size": 12 }, "Time (ps)"));
      columns.forEach((values, index) => {
        if (!visible[index]) return;
        const points = [];
        for (let i = start; i < end; i++) points.push(`${x(time[i])},${y(values[i])}`);
        svg.append(svgNode("polyline", { "data-series": names[kind][index], "data-first-sample": start,
          "data-last-sample": end - 1, fill: "none", stroke: colors[index], "stroke-width": 1.6,
          "stroke-dasharray": index < 2 ? "none" : "5 3", points: points.join(" ") }));
        if (end - start === 1) svg.append(svgNode("circle", { cx: x(time[start]), cy: y(values[start]), r: 3, fill: colors[index] }));
      });
      if (!visible.some(Boolean)) svg.append(svgNode("text", { x: (left + right) / 2, y: 135, "text-anchor": "middle", fill: "#55625d", "font-size": 13 }, "No stages selected"));
      cursorLine = svgNode("line", { y1: top, y2: bottom, stroke: "#66746c", "stroke-width": 1, "stroke-dasharray": "3 4", "data-cursor": "" });
      svg.append(cursorLine);
      status.textContent = `Samples ${start}..${end - 1} of ${time.length} | ${end - start} original points | ${unit}`;
      section.dataset.firstSample = String(start);
      section.dataset.lastSample = String(end - 1);
      controls.start.value = controls.position.value = String(start);
      controls.start.max = controls.position.max = String(time.length - 1);
      controls.count.value = String(count);
      cursor = clamp(cursor, start, end - 1);
      readCursor();
    }

    function moveStart(input) {
      start = integer(input, start, 0, time.length - 1);
      draw();
    }
    controls.start.addEventListener("change", () => moveStart(controls.start));
    controls.position.addEventListener("input", () => moveStart(controls.position));
    controls.count.addEventListener("change", () => {
      count = integer(controls.count, count, 1, Math.min(4096, time.length));
      draw();
    });
    controls.cursor.addEventListener("change", () => {
      cursor = integer(controls.cursor, cursor, 0, time.length - 1);
      if (cursor < start || cursor >= start + count) start = clamp(cursor - Math.floor(count / 2), 0, Math.max(0, time.length - count));
      draw();
    });
    svg.addEventListener("pointermove", event => {
      const bounds = svg.getBoundingClientRect();
      const fraction = clamp((event.clientX - bounds.left - geometry.left) / (geometry.right - geometry.left), 0, 1);
      cursor = start + Math.round(fraction * (Math.min(time.length, start + count) - start - 1));
      readCursor();
    });
    section.classList.add("interactive");
    section.querySelector(".controls").hidden = table.hidden = false;
    draw();
    new ResizeObserver(draw).observe(section.querySelector(".plot"));
  }
  document.documentElement.dataset.channelReportReady = "true";
})();
