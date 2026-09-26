/* Learn Git Branching — static client (Pyodide + lgb package). */

const bootStatus = document.getElementById("boot-status");
const graphEl = document.getElementById("graph");
const terminalEl = document.getElementById("terminal");
const cmdForm = document.getElementById("cmd-form");
const cmdInput = document.getElementById("cmd-input");
const helpBox = document.getElementById("help-box");
const levelPanel = document.getElementById("level-panel");
const levelName = document.getElementById("level-name");
const levelLesson = document.getElementById("level-lesson");
const levelHint = document.getElementById("level-hint");
const levelGolf = document.getElementById("level-golf");
const solutionBox = document.getElementById("solution-box");
const goalGraph = document.getElementById("goal-graph");
const winBanner = document.getElementById("win-banner");
const levelNav = document.getElementById("level-nav");
const progressEl = document.getElementById("progress");
const cmdCountEl = document.getElementById("cmd-count");
const modeButtons = [...document.querySelectorAll(".mode-btn")];

const MODULE_FILES = [
  "lgb/__init__.py",
  "lgb/model.py",
  "lgb/commands.py",
  "lgb/tree_io.py",
  "lgb/goal.py",
  "lgb/viz.py",
  "lgb/levels.py",
  "bridge.py",
];

let pyodide = null;

function setBoot(text) {
  bootStatus.textContent = text;
}

async function loadSourceFiles() {
  pyodide.FS.mkdirTree("/lgb");
  for (const path of MODULE_FILES) {
    const res = await fetch(`./${path}`);
    if (!res.ok) {
      throw new Error(`failed to fetch ${path}: ${res.status}`);
    }
    const text = await res.text();
    pyodide.FS.writeFile(`/${path}`, text);
  }
}

function pySession() {
  return pyodide.globals.get("session");
}

function refresh() {
  const session = pySession();
  const status = JSON.parse(session.status_json());
  terminalEl.textContent = session.terminal_text();
  graphEl.innerHTML = session.graph_svg();

  modeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === status.mode);
  });

  if (status.mode === "levels") {
    levelPanel.classList.remove("hidden");
    levelName.textContent = status.name;
    levelLesson.textContent = status.lesson;
    levelHint.textContent = status.hint;
    levelGolf.textContent = `Target: ${status.golf_target} commands · You: ${status.command_count}${
      status.best != null ? ` · Best: ${status.best}` : ""
    }`;
    solutionBox.textContent = status.solution;
    solutionBox.classList.toggle("hidden", !status.show_solution);
    winBanner.classList.toggle("hidden", !status.solved);
    goalGraph.innerHTML = session.goal_svg();
    levelNav.innerHTML = "";
    if (status.solved && status.next_level) {
      const nextBtn = document.createElement("button");
      nextBtn.className = "btn primary";
      nextBtn.textContent = "Next level";
      nextBtn.addEventListener("click", () => {
        session.load_level(status.next_level);
        refresh();
      });
      levelNav.appendChild(nextBtn);
    }
    const catBtn = document.createElement("button");
    catBtn.className = "btn";
    catBtn.textContent = "Back to catalog";
    catBtn.addEventListener("click", () => {
      session.set_mode("catalog");
      renderCatalog();
    });
    levelNav.appendChild(catBtn);
  } else {
    levelPanel.classList.add("hidden");
    if (status.mode === "catalog") {
      renderCatalog();
    }
  }

  progressEl.textContent = `${status.solved_count} / ${status.level_count} levels solved`;
  cmdCountEl.textContent = String(status.command_count);
}

function renderCatalog() {
  const session = pySession();
  const items = JSON.parse(session.catalog_json());
  const bySeq = new Map();
  for (const item of items) {
    if (!bySeq.has(item.sequence)) {
      bySeq.set(item.sequence, {
        title: item.sequence_title,
        blurb: item.sequence_blurb,
        rows: [],
      });
    }
    bySeq.get(item.sequence).rows.push(item);
  }

  const host = document.createElement("div");
  host.className = "catalog";
  const heading = document.createElement("h2");
  heading.textContent = "Levels";
  host.appendChild(heading);
  const intro = document.createElement("p");
  intro.className = "seq-blurb";
  intro.textContent =
    "Pick a sequence, then a challenge. Best command count is kept for this session (git golf).";
  host.appendChild(intro);

  for (const group of bySeq.values()) {
    const h = document.createElement("h2");
    h.textContent = group.title;
    host.appendChild(h);
    const blurb = document.createElement("p");
    blurb.className = "seq-blurb";
    blurb.textContent = group.blurb;
    host.appendChild(blurb);

    for (const row of group.rows) {
      const div = document.createElement("div");
      div.className = "level-row";
      div.innerHTML = `
        <div>
          <div class="title"><strong>${row.name}</strong></div>
          <div class="sub">${row.hint}</div>
        </div>
        <div class="sub">golf ${row.golf_target}${
          row.best != null ? ` · best ${row.best}` : ""
        }${row.solved ? " · solved" : ""}</div>
      `;
      const btn = document.createElement("button");
      btn.className = "btn primary";
      btn.textContent = "Play";
      btn.addEventListener("click", () => {
        pySession().load_level(row.id);
        refresh();
      });
      div.appendChild(btn);
      host.appendChild(div);
    }
  }

  // Replace any previous catalog block
  const old = document.querySelector(".catalog");
  if (old) old.remove();
  const main = document.querySelector(".main");
  main.insertBefore(host, main.firstChild);
  graphEl.innerHTML = "";
}

function bindUi() {
  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.mode;
      pySession().set_mode(mode);
      if (mode === "catalog") {
        const old = document.querySelector(".catalog");
        if (old) old.remove();
        renderCatalog();
        terminalEl.textContent = pySession().terminal_text();
      } else {
        const old = document.querySelector(".catalog");
        if (old) old.remove();
        refresh();
      }
    });
  });

  cmdForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const line = cmdInput.value;
    cmdInput.value = "";
    pySession().run(line);
    const old = document.querySelector(".catalog");
    if (old) old.remove();
    refresh();
  });

  document.getElementById("btn-undo").addEventListener("click", () => {
    pySession().undo();
    refresh();
  });

  document.getElementById("btn-reset").addEventListener("click", () => {
    pySession().reset();
    refresh();
  });

  document.getElementById("btn-reset-level").addEventListener("click", () => {
    pySession().reset();
    refresh();
  });

  document.getElementById("btn-solution").addEventListener("click", () => {
    pySession().reveal_solution();
    refresh();
  });
}

async function boot() {
  try {
    setBoot("loading Pyodide…");
    pyodide = await loadPyodide();
    setBoot("loading lgb package…");
    await loadSourceFiles();
    pyodide.runPython("import sys\nsys.path.insert(0, '/')\n");
    pyodide.runPython("import bridge\nsession = bridge.session\n");
    helpBox.textContent = pySession().help_text();
    bindUi();
    refresh();
    setBoot("ready");
    cmdInput.focus();
  } catch (err) {
    console.error(err);
    setBoot("failed to load");
    terminalEl.textContent = `Failed to start: ${err.message}`;
  }
}

boot();
