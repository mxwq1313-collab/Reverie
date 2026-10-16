"use strict";

const $ = (id) => document.getElementById(id);
const state = { users: [], viewer: null, peer: null, contacts: [], contactTotal: 0, messageCount: 0, total: 0, messages: [], filters: {}, messageVersion: 0, contactVersion: 0, bootVersion: 0, controller: null, loading: false };
const dateOptions = { timeZone: "Asia/Shanghai", year: "numeric", month: "long", day: "numeric", weekday: "long" };
const timeOptions = { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hour12: false };
const localDate = (time) => new Date(time).toLocaleDateString("zh-CN", dateOptions);
const localTime = (time) => new Date(time).toLocaleTimeString("zh-CN", timeOptions);

function node(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}

async function api(path, params = {}, signal) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  let response;
  try { response = await fetch(`${path}?${query}`, { signal, cache: "no-store" }); }
  catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("连接已断开。请确认启动窗口仍在运行，再点击重试。");
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || "读取记录失败，请重试。");
  return data;
}

function showEmpty(title, description, retry = false) {
  $("empty-state").hidden = false;
  $("empty-title").textContent = title;
  $("empty-description").textContent = description;
  $("retry").hidden = !retry;
}

function updateHeading() {
  const all = $("scope").value === "all";
  const peer = state.users.find((user) => user.id === state.peer);
  const viewer = state.users.find((user) => user.id === state.viewer);
  $("chat-title").textContent = all ? "全部聊天" : (peer?.nickname || "你的对话，在这里重逢");
  $("chat-subtitle").textContent = all ? `查看 ${viewer?.nickname || "当前身份"} 参与的所有对话` : (peer ? `${peer.wxid} · 双向聊天记录` : "选择联系人，回看聊天记录");
  $("chat-avatar").textContent = all ? "全" : (peer?.nickname?.slice(0, 1) || "语");
}

function renderContacts() {
  $("contacts").replaceChildren();
  $("contact-count").textContent = `${state.contactTotal} 位`;
  for (const contact of state.contacts) {
    const button = node("button", `contact${contact.id === state.peer && $("scope").value !== "all" ? " active" : ""}`);
    button.type = "button";
    button.setAttribute("aria-pressed", String(contact.id === state.peer && $("scope").value !== "all"));
    button.setAttribute("aria-label", `${contact.nickname}，${contact.message_count} 条消息`);
    const avatar = node("span", `avatar tone-${contact.id % 4}`, contact.nickname.slice(0, 1));
    avatar.setAttribute("aria-hidden", "true");
    const detail = node("span", "contact-detail");
    const title = node("span", "contact-title");
    title.append(node("span", "contact-name", contact.nickname), node("span", "contact-count", contact.message_count));
    detail.append(title, node("p", "contact-preview", contact.last_message || "还没有聊天记录"));
    button.append(avatar, detail);
    button.addEventListener("click", () => selectPeer(contact.id));
    $("contacts").append(button);
  }
  if (!state.contacts.length) $("contacts").append(node("p", "sidebar-note", $("contact-search").value ? "没有找到匹配的联系人" : "还没有可查看的联系人"));
  $("more-contacts").hidden = state.contacts.length >= state.contactTotal;
}

async function loadContacts(append = false) {
  if (!state.viewer) return;
  const version = ++state.contactVersion;
  $("more-contacts").disabled = true;
  try {
    const data = await api("/api/contacts", { user_id: state.viewer, q: $("contact-search").value.trim(), limit: 50, offset: append ? state.contacts.length : 0 });
    if (version !== state.contactVersion) return;
    state.contacts = append ? state.contacts.concat(data.items) : data.items;
    state.contactTotal = data.total;
    renderContacts();
  } catch (error) {
    if (version !== state.contactVersion) return;
    $("contacts").replaceChildren(node("p", "sidebar-note", error.message));
  } finally {
    if (version === state.contactVersion) $("more-contacts").disabled = false;
  }
}

function renderMessages() {
  $("messages").replaceChildren();
  let lastDate = "";
  for (const message of state.messages) {
    const date = localDate(message.create_time);
    if (date !== lastDate) { $("messages").append(node("div", "date-label", date)); lastDate = date; }
    const mine = message.sender_id === state.viewer;
    const row = node("article", `message${mine ? " mine" : ""}`);
    const avatar = node("span", `avatar tone-${message.sender_id % 4}`, message.sender_name.slice(0, 1));
    avatar.setAttribute("aria-hidden", "true");
    const body = node("div", "message-body");
    if ($("scope").value === "all") {
      const peerId = mine ? message.receiver_id : message.sender_id;
      const peer = state.users.find((user) => user.id === peerId);
      const context = node("button", "message-context", `与 ${peer?.nickname || "联系人"} 的聊天 →`);
      context.type = "button";
      context.addEventListener("click", () => selectPeer(peerId));
      body.append(context);
    }
    const senderLabel = mine && message.sender_name !== "我" ? `${message.sender_name} · 我` : message.sender_name;
    body.append(node("div", "message-name", senderLabel));
    // 聊天内容只作为文本展示，HTML 标签不会执行。
    body.append(node("div", "bubble", message.content), node("div", "message-time", localTime(message.create_time)));
    row.append(avatar, body);
    $("messages").append(row);
  }
}

async function loadMessages(append = false) {
  if (!state.viewer) return;
  const peerId = $("scope").value === "all" ? null : state.peer;
  if (peerId === null && $("scope").value !== "all") {
    $("messages").replaceChildren();
    $("result-summary").textContent = "尚未选择联系人";
    showEmpty("选择一位联系人", "点击左侧联系人，回看你们的双向聊天。");
    return;
  }
  const version = ++state.messageVersion;
  if (state.controller) state.controller.abort();
  state.controller = new AbortController();
  state.loading = true;
  $("load-more").disabled = true;
  if (!append) {
    state.messages = [];
    $("messages").replaceChildren();
    $("empty-state").hidden = true;
    $("load-more").hidden = true;
    $("page-info").textContent = "正在读取…";
  }
  $("result-summary").textContent = "正在读取记录…";
  const oldScroll = $("timeline").scrollTop;
  try {
    const data = await api("/api/messages", { user_id: state.viewer, peer_id: peerId, ...state.filters, limit: 50, offset: append ? state.messages.length : 0 }, state.controller.signal);
    if (version !== state.messageVersion) return;
    state.messages = append ? state.messages.concat(data.items) : data.items;
    state.total = data.total;
    renderMessages();
    $("empty-state").hidden = state.messages.length > 0;
    if (!state.messages.length) showEmpty(Object.keys(state.filters).length ? "没有找到匹配的消息" : "这段聊天还没有记录", Object.keys(state.filters).length ? "换一个关键词，或清除日期筛选再试试。" : "保存聊天数据后，点击右上角刷新即可查看。");
    $("result-summary").textContent = `共 ${data.total} 条消息`;
    $("page-info").textContent = `已显示 ${state.messages.length} / ${data.total} 条`;
    $("load-more").hidden = !data.has_more;
    $("filter-state").textContent = Object.keys(state.filters).length ? "筛选结果 · 按时间排列" : "按时间先后排列";
    $("timeline").scrollTop = append ? oldScroll : 0;
  } catch (error) {
    if (version !== state.messageVersion || error.name === "AbortError") return;
    $("result-summary").textContent = "读取失败";
    $("page-info").textContent = "请重试";
    showEmpty("暂时无法读取记录", error.message, true);
  } finally {
    if (version === state.messageVersion) { state.loading = false; $("load-more").disabled = false; }
  }
}

function selectPeer(id) {
  state.peer = id;
  $("scope").value = "current";
  updateHeading();
  renderContacts();
  loadMessages();
}

function clearFilterInputs() {
  $("message-search").value = "";
  $("start-date").value = "";
  $("end-date").value = "";
  $("filter-error").hidden = true;
  state.filters = {};
}

function applyFilters(event) {
  if (event) event.preventDefault();
  const start = $("start-date").value;
  const end = $("end-date").value;
  if (start && end && start > end) {
    $("filter-error").textContent = "开始日期不能晚于结束日期。";
    $("filter-error").hidden = false;
    return;
  }
  $("filter-error").hidden = true;
  state.filters = {};
  const q = $("message-search").value.trim();
  if (q) state.filters.q = q;
  if (start) state.filters.start = `${start}T00:00:00+08:00`;
  if (end) {
    const nextDay = new Date(`${end}T00:00:00Z`);
    nextDay.setUTCDate(nextDay.getUTCDate() + 1);
    state.filters.end = `${nextDay.toISOString().slice(0, 10)}T00:00:00+08:00`;
  }
  updateHeading();
  renderContacts();
  loadMessages();
}

async function boot() {
  const version = ++state.bootVersion;
  ++state.contactVersion;
  ++state.messageVersion;
  if (state.controller) state.controller.abort();
  $("connection-error").hidden = true;
  $("refresh").disabled = true;
  try {
    const status = await api("/api/status");
    const users = [];
    let page;
    do { page = await api("/api/users", { limit: 1000, offset: users.length }); users.push(...page.items); } while (page.has_more);
    if (version !== state.bootVersion) return;
    state.users = users;
    $("mode").textContent = status.mode === "demo" ? "演示数据" : "本地归档";
    $("mode").classList.toggle("demo", status.mode === "demo");
    $("archive-stats").textContent = `${status.users} 位参与者 · ${status.messages} 条消息`;
    $("identity").replaceChildren();
    users.forEach((user) => { const option = node("option", "", user.nickname); option.value = user.id; $("identity").append(option); });
    $("identity").disabled = !users.length;
    if (!users.length) {
      state.viewer = null; state.peer = null; state.contacts = []; state.contactTotal = 0;
      $("identity").append(node("option", "", "还没有参与者"));
      renderContacts(); updateHeading();
      $("messages").replaceChildren(); $("load-more").hidden = true;
      $("result-summary").textContent = "归档库为空"; $("page-info").textContent = "0 条消息";
      showEmpty("这里还没有聊天记录", "当前归档库为空。可双击 Run-Web-Demo.cmd 体验演示数据，或添加数据后点击刷新。");
      return;
    }
    state.viewer = users.some((user) => user.id === state.viewer) ? state.viewer : users[0].id;
    $("identity").value = state.viewer;
    await loadContacts();
    if (version !== state.bootVersion) return;
    if (!state.users.some((user) => user.id === state.peer)) state.peer = state.contacts[0]?.id ?? null;
    renderContacts(); updateHeading();
    await loadMessages();
  } catch (error) {
    if (version !== state.bootVersion) return;
    $("connection-error").textContent = error.message;
    $("connection-error").hidden = false;
    $("result-summary").textContent = "连接失败";
    showEmpty("暂时无法连接归档", error.message, true);
  } finally { if (version === state.bootVersion) $("refresh").disabled = false; }
}

$("identity").addEventListener("change", async () => {
  state.viewer = Number($("identity").value); state.peer = null;
  state.contacts = []; state.contactTotal = 0;
  clearFilterInputs(); $("contact-search").value = ""; $("scope").value = "current";
  // 立即取消旧身份的读取，防止切换过程中出现旧会话内容。
  ++state.messageVersion; if (state.controller) state.controller.abort();
  $("messages").replaceChildren(); updateHeading(); renderContacts();
  const viewer = state.viewer;
  await loadContacts();
  if (viewer !== state.viewer) return;
  state.peer = state.contacts[0]?.id ?? null;
  renderContacts(); updateHeading(); await loadMessages();
});
let contactTimer;
$("contact-search").addEventListener("input", () => { clearTimeout(contactTimer); contactTimer = setTimeout(() => loadContacts(), 250); });
$("more-contacts").addEventListener("click", () => loadContacts(true));
$("filters").addEventListener("submit", applyFilters);
$("scope").addEventListener("change", applyFilters);
$("clear-filters").addEventListener("click", () => { clearFilterInputs(); applyFilters(); });
$("load-more").addEventListener("click", () => { if (!state.loading) loadMessages(true); });
$("refresh").addEventListener("click", boot);
$("retry").addEventListener("click", boot);
boot();
