const tg = window.Telegram?.WebApp;

const API_URL = "https://storied-bubblegum-a94e6a.netlify.app"; // ← ПОКА ТАК

let user;

if (tg) {
  tg.ready();
  tg.expand();
  user = tg.initDataUnsafe.user;
} else {
  // browser fallback
  user = { id: 999999 };
}

async function api(path, data = {}) {
  const res = await fetch(API_URL + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: user.id,
      ...data
    })
  });
  return res.json();
}

async function loadHabits() {
  const habits = await api("/api/habits");
  const root = document.getElementById("habits");
  root.innerHTML = "";

  habits.forEach(h => {
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `
      <b>${h.title}</b><br/>
      🔥 Серия: ${h.streak}<br/><br/>
      <button onclick="done(${h.id})">✅ Выполнено</button>
      <button class="danger" onclick="del(${h.id})">🗑 Удалить</button>
    `;
    root.appendChild(div);
  });
}

async function done(id) {
  await api("/api/done", { habit_id: id });
  loadHabits();
}

async function del(id) {
  await api("/api/delete", { habit_id: id });
  loadHabits();
}

loadHabits();
