import {
  AlertTriangle,
  Archive,
  ArrowLeft,
  Check,
  Copy,
  Download,
  FileText,
  Image,
  Info,
  Mic,
  Music,
  Paperclip,
  Pencil,
  CalendarDays,
  Target,
  Users,
  BookOpen,
  User,
  Reply,
  Search,
  Send,
  SlidersHorizontal,
  Square,
  Trash2,
  Video,
  X,
} from "lucide-react";
import * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || `${window.location.origin}/api`;
const WS_BASE = import.meta.env.VITE_WS_BASE || `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
const ADMIN_SECTION_STORAGE_KEY = "uknow-miniapp-admin-section";
const SCROLL_SAFE_AREA_CLASS = "pb-[calc(1rem+env(safe-area-inset-bottom))]";
const FILTERS = [
  { id: "all", label: "Усі" },
  { id: "unread", label: "Непрочитані" },
  { id: "waiting", label: "Чекають відповіді" },
  { id: "archive", label: "Архів" },
];
const LESSON_FILTERS = [
  { id: "today", label: "Сьогодні" },
  { id: "week", label: "Тиждень" },
  { id: "calendar", label: "Календар" },
  { id: "all", label: "Усі" },
];

export default function TeacherWorkspace() {
  const [role, setRole] = useState("teacher");
  const [wsToken, setWsToken] = useState("");
  const [chats, setChats] = useState([]);
  const [lessons, setLessons] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [messages, setMessages] = useState([]);
  const [selectedChatId, setSelectedChatId] = useState(null);
  const [activeSection, setActiveSection] = useState("chats");
  const [query, setQuery] = useState("");
  const [messageQuery, setMessageQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [teacherFilter, setTeacherFilter] = useState("all");
  const [lessonFilter, setLessonFilter] = useState("week");
  const [text, setText] = useState("");
  const [status, setStatus] = useState("connecting");
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [authError, setAuthError] = useState("");
  const [replyingTo, setReplyingTo] = useState(null);
  const [editingMessage, setEditingMessage] = useState(null);
  const [infoOpen, setInfoOpen] = useState(false);

  const wsRef = useRef(null);
  const selectedChatIdRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const fileInputRef = useRef(null);

  const selectedChat = useMemo(
    () => chats.find((chat) => chat.id === selectedChatId) || null,
    [chats, selectedChatId],
  );

  const navSections = useMemo(() => (
    role === "admin"
      ? [
          { id: "admin", label: "Адмін", icon: <SlidersHorizontal size={18} /> },
          { id: "chats", label: "Чати", icon: <MessageIcon /> },
          { id: "students", label: "Учні", icon: <Users size={18} /> },
          { id: "lessons", label: "Уроки", icon: <BookOpen size={18} /> },
          { id: "profile", label: "Профіль", icon: <User size={18} /> },
        ]
      : [
          { id: "chats", label: "Чати", icon: <MessageIcon /> },
          { id: "students", label: "Учні", icon: <Users size={18} /> },
          { id: "lessons", label: "Уроки", icon: <BookOpen size={18} /> },
          { id: "profile", label: "Профіль", icon: <User size={18} /> },
        ]
  ), [role]);

  const teacherOptions = useMemo(() => teachers, [teachers]);

  const filteredChats = useMemo(() => {
    const value = query.trim().toLowerCase();
    return chats.filter((chat) => {
      if (activeFilter !== "archive" && chat.is_archived) return false;
      if (activeFilter === "archive" && !chat.is_archived) return false;
      if (activeFilter === "unread" && !chat.unread_count) return false;
      if (activeFilter === "waiting" && !chat.waiting_reply) return false;
      if (teacherFilter !== "all" && String(chat.teacher_id || "") !== teacherFilter) return false;
      if (!value) return true;
      return `${chat.title} ${chat.username} ${chat.language} ${chat.level} ${chat.teacher_name}`.toLowerCase().includes(value);
    });
  }, [activeFilter, chats, query, teacherFilter]);

  const visibleMessages = useMemo(() => {
    const value = messageQuery.trim().toLowerCase();
    return messages.filter((message) => {
      if (String(message.chat_id) !== String(selectedChatId)) return false;
      if (!value) return true;
      return `${message.text} ${message.original_text} ${message.filename} ${message.sender_name}`.toLowerCase().includes(value);
    });
  }, [messageQuery, messages, selectedChatId]);

  useEffect(() => {
    selectedChatIdRef.current = selectedChatId;
  }, [selectedChatId]);

  useEffect(() => {
    if (role !== "admin") return;
    if (!isAdminSection(activeSection)) return;
    window.localStorage.setItem(ADMIN_SECTION_STORAGE_KEY, activeSection);
  }, [activeSection, role]);

  useEffect(() => {
    let cancelled = false;
    let reconnectTimer = null;

    function openSocket(wsTokenValue) {
      const ws = new WebSocket(`${WS_BASE}/ws/teacher/?token=${encodeURIComponent(wsTokenValue)}`);
      wsRef.current = ws;

      ws.onopen = () => setStatus("online");
      ws.onclose = () => {
        setStatus("offline");
        if (!cancelled) {
          reconnectTimer = window.setTimeout(() => openSocket(wsTokenValue), 1500);
        }
      };
      ws.onerror = () => setStatus("offline");
      ws.onmessage = (event) => handleWsMessage(JSON.parse(event.data));
    }

    async function connect() {
      try {
        const initData = window.Telegram?.WebApp?.initData || "";
        const urlParams = new URLSearchParams(window.location.search);
        const startParam = window.Telegram?.WebApp?.initDataUnsafe?.start_param || urlParams.get("startapp") || urlParams.get("chat") || "";
        const response = await fetch(`${API_BASE}/miniapp/auth/`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ initData }),
        });

        if (!response.ok) throw new Error(await readApiError(response, "Помилка авторизації Mini App"));
        const { ws_token } = await response.json();
        setWsToken(ws_token);
        setAuthError("");
        if (cancelled) return;

        const bootstrapResponse = await fetch(`${API_BASE}/miniapp/bootstrap/`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ token: ws_token }),
        });
        if (!bootstrapResponse.ok) throw new Error(await readApiError(bootstrapResponse, "Не вдалося завантажити Mini App"));
        const bootstrap = await bootstrapResponse.json();
        const initialChatId = chatIdFromStartParam(startParam);
        setRole(bootstrap.role || "teacher");
        setChats(bootstrap.chats || []);
        setLessons(bootstrap.lessons || []);
        setTeachers(bootstrap.teachers || []);
        setMessages(bootstrap.messages || []);
        if (bootstrap.role === "admin") {
          setActiveSection(getStoredAdminSection());
        }
        if (initialChatId) setSelectedChatId(initialChatId);

        openSocket(ws_token);
      } catch (error) {
        setAuthError(error.message || "Не вдалося відкрити Mini App");
        setStatus("offline");
      }
    }

    window.Telegram?.WebApp?.ready();
    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, []);

  useEffect(() => {
    if (!wsToken) return undefined;
    let cancelled = false;

    async function refreshBootstrap() {
      try {
        const response = await fetch(`${API_BASE}/miniapp/bootstrap/`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ token: wsToken }),
        });
        if (response.status === 401 || response.status === 403) {
          setAuthError(await readApiError(response, "Доступ до Mini App відхилено"));
          setStatus("offline");
          return;
        }
        if (!response.ok || cancelled) return;
        const payload = await response.json();
        setRole(payload.role || "teacher");
        setChats(payload.chats || []);
        setLessons(payload.lessons || []);
        setTeachers(payload.teachers || []);
        setMessages(payload.messages || []);
        setAuthError("");
      } catch {
        // WebSocket remains the primary channel; polling is only a quiet fallback.
      }
    }

    const intervalId = window.setInterval(refreshBootstrap, 3000);
    window.addEventListener("focus", refreshBootstrap);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", refreshBootstrap);
    };
  }, [wsToken]);

  useEffect(() => {
    if (!selectedChatId || status !== "online") return;
    markChatReadLocally(selectedChatId);
    wsRef.current?.send(JSON.stringify({ type: "chat.read", chat_id: selectedChatId }));
    persistChatRead(selectedChatId);
  }, [selectedChatId, status, wsToken]);

  function handleWsMessage(data) {
    if (data.type === "chat.history") {
      setChats(data.chats || []);
      setMessages(data.messages || []);
      setLessons(data.lessons || []);
      return;
    }

    if (data.type === "chat.message") {
      setMessages((current) => {
        const next = upsertMessage(current, data.message);
        const chatIsOpen = String(selectedChatIdRef.current) === String(data.message.chat_id);
        const unreadDelta = data.message.sender_kind === "student" && !chatIsOpen ? 1 : 0;
        setChats((chatsCurrent) => syncChatFromMessages(chatsCurrent, data.message.chat_id, next, {
          unreadDelta,
          clearUnread: chatIsOpen,
        }));
        return next;
      });
      return;
    }

    if (data.type === "chat.edit") {
      if (!data.message) return;
      setMessages((current) => {
        const next = upsertMessage(current, data.message);
        setChats((chatsCurrent) => syncChatFromMessages(chatsCurrent, data.message.chat_id, next, {
          clearUnread: String(selectedChatIdRef.current) === String(data.message.chat_id),
        }));
        return next;
      });
      return;
    }

    if (data.type === "chat.delete") {
      if (data.message) {
        setMessages((current) => {
          const next = upsertMessage(current, data.message);
          setChats((chatsCurrent) => syncChatFromMessages(chatsCurrent, data.message.chat_id, next, {
            clearUnread: String(selectedChatIdRef.current) === String(data.message.chat_id),
          }));
          return next;
        });
      } else if (data.message_id) {
        setMessages((current) => {
          const { messages: next, chatId } = markMessageDeletedLocally(current, data.message_id);
          if (chatId) setChats((chatsCurrent) => syncChatFromMessages(chatsCurrent, chatId, next, {
            clearUnread: String(selectedChatIdRef.current) === String(chatId),
          }));
          return next;
        });
      }
      return;
    }

    if (data.type === "chat.read") {
      setChats((current) => current.map((chat) => (
        String(chat.id) === String(data.chat_id) ? { ...chat, unread_count: 0 } : chat
      )));
    }
  }

  function markChatReadLocally(chatId) {
    setChats((current) => current.map((chat) => (
      String(chat.id) === String(chatId) ? { ...chat, unread_count: 0 } : chat
    )));
  }

  async function persistChatRead(chatId) {
    if (!wsToken || !chatId) return;
    try {
      await fetch(`${API_BASE}/miniapp/chat/read/`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ token: wsToken, student_id: String(chatId) }),
      });
    } catch {
      // Local UI already reflects the read state; polling/WS will retry later.
    }
  }

  function openChat(chatId) {
    setActiveSection("chats");
    setSelectedChatId(chatId);
    markChatReadLocally(chatId);
    setInfoOpen(false);
    setReplyingTo(null);
    setEditingMessage(null);
    loadChatHistory(chatId);
    wsRef.current?.send(JSON.stringify({ type: "chat.read", chat_id: chatId }));
    persistChatRead(chatId);
  }

  function sendText() {
    const value = text.trim();
    if (!value || !selectedChatId) return;

    if (editingMessage) {
      wsRef.current?.send(JSON.stringify({
        type: "chat.edit",
        message_id: editingMessage.id,
        text: value,
      }));
      setEditingMessage(null);
    } else {
      wsRef.current?.send(JSON.stringify({
        type: "chat.message",
        chat_id: selectedChatId,
        text: value,
        reply_to_message_id: replyingTo?.id || null,
      }));
      markChatReadLocally(selectedChatId);
      setReplyingTo(null);
    }
    setText("");
  }

  function startEdit(message) {
    setEditingMessage(message);
    setReplyingTo(null);
    setText(message.original_text || message.text || "");
  }

  async function sendFiles(files) {
    if (!selectedChatId || !wsToken) return;
    const selectedFiles = Array.from(files || []);
    if (!selectedFiles.length || uploading) return;

    setUploading(true);
    setUploadError("");
    try {
      for (const file of selectedFiles) {
        const formData = new FormData();
        formData.append("token", wsToken);
        formData.append("student_id", String(selectedChatId));
        formData.append("file", file);
        formData.append("caption", text.trim());
        if (replyingTo?.id) formData.append("reply_to_message_id", String(replyingTo.id));

        const response = await fetch(`${API_BASE}/miniapp/attachment/upload/`, {
          method: "POST",
          body: formData,
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || "Не вдалося прикріпити файл");
        }
        const payload = await response.json();
        if (payload.message) {
          setMessages((current) => {
            const next = upsertMessage(current, payload.message);
            setChats((chatsCurrent) => syncChatFromMessages(chatsCurrent, payload.message.chat_id, next, {
              clearUnread: String(selectedChatIdRef.current) === String(payload.message.chat_id),
            }));
            return next;
          });
        }
      }
      setText("");
      setReplyingTo(null);
    } catch (error) {
      setUploadError(error.message || "Не вдалося прикріпити файл");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    if (!selectedChatId) return;

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    chunksRef.current = [];

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };

    recorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      const audioBase64 = await blobToDataUrl(blob);
      wsRef.current?.send(JSON.stringify({
        type: "chat.voice",
        chat_id: selectedChatId,
        audio_base64: audioBase64,
        reply_to_message_id: replyingTo?.id || null,
      }));
      setReplyingTo(null);
      stream.getTracks().forEach((track) => track.stop());
    };

    recorderRef.current = recorder;
    recorder.start();
    setRecording(true);
  }

  function deleteMessage(messageId) {
    fetch(`${API_BASE}/miniapp/message/delete/`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ token: wsToken, message_id: String(messageId) }),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("delete failed");
        const payload = await response.json();
        if (!payload.message) throw new Error("delete failed");
        setMessages((current) => {
          const next = upsertMessage(current, payload.message);
          setChats((chatsCurrent) => syncChatFromMessages(chatsCurrent, payload.message.chat_id, next, {
            clearUnread: String(selectedChatIdRef.current) === String(payload.message.chat_id),
          }));
          return next;
        });
      })
      .catch(() => {
        wsRef.current?.send(JSON.stringify({
          type: "chat.delete",
          message_id: messageId,
        }));
      });
  }

  async function updateStudent(chatId, values) {
    if (!wsToken) return;
    const response = await fetch(`${API_BASE}/miniapp/student/update/`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        token: wsToken,
        student_id: String(chatId),
        ...values,
      }),
    });
    if (response.ok) {
      const payload = await response.json();
      setChats(payload.chats || []);
      if (payload.teachers) setTeachers(payload.teachers || []);
    }
  }

  async function loadMessageEdits(messageId) {
    if (!wsToken) return [];
    const response = await fetch(`${API_BASE}/miniapp/message/edits/`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ token: wsToken, message_id: String(messageId) }),
    });
    if (!response.ok) return [];
    const payload = await response.json();
    return payload.edits || [];
  }

  async function loadChatHistory(chatId) {
    if (!wsToken) return;
    const response = await fetch(`${API_BASE}/miniapp/chat/history/`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ token: wsToken, student_id: String(chatId) }),
    });
    if (!response.ok) return;
    const payload = await response.json();
    const history = payload.messages || [];
    setMessages((current) => {
      const preserved = current.filter((message) => String(message.chat_id) !== String(chatId));
      return [...preserved, ...history];
    });
  }

  return (
    <div className="h-[100dvh] bg-[#eef2f5] text-[#111827]">
      <div className="mx-auto grid h-full max-w-6xl overflow-hidden bg-white shadow-sm md:grid-cols-[380px_1fr] md:border-x md:border-zinc-200">
        <ChatList
          role={role}
          chats={filteredChats}
          allChats={chats}
          query={query}
          setQuery={setQuery}
          activeFilter={activeFilter}
          setActiveFilter={setActiveFilter}
          teacherOptions={teacherOptions}
          teacherFilter={teacherFilter}
          setTeacherFilter={setTeacherFilter}
          activeSection={activeSection}
          setActiveSection={setActiveSection}
          selectedChatId={selectedChatId}
          openChat={openChat}
          navSections={navSections}
          hiddenOnMobile={Boolean(selectedChatId) || activeSection !== "chats"}
        />

        {authError ? <ErrorPanel message={authError} /> : activeSection === "admin" ? <AdminPanel
          role={role}
          chats={chats}
          allChats={chats}
          teachers={teacherOptions}
          openChat={openChat}
          setActiveSection={setActiveSection}
          setTeacherFilter={setTeacherFilter}
          setActiveFilter={setActiveFilter}
          back={() => setActiveSection("chats")}
        /> : activeSection === "chats" ? <ChatPanel
          role={role}
          chat={selectedChat}
          messages={visibleMessages}
          messageQuery={messageQuery}
          setMessageQuery={setMessageQuery}
          status={status}
          text={text}
          setText={setText}
          sendText={sendText}
          recording={recording}
          toggleRecording={toggleRecording}
          deleteMessage={deleteMessage}
          replyingTo={replyingTo}
          setReplyingTo={setReplyingTo}
          editingMessage={editingMessage}
          setEditingMessage={setEditingMessage}
          startEdit={startEdit}
          fileInputRef={fileInputRef}
          sendFiles={sendFiles}
          uploading={uploading}
          uploadError={uploadError}
          clearUploadError={() => setUploadError("")}
          infoOpen={infoOpen}
          setInfoOpen={setInfoOpen}
          updateStudent={updateStudent}
          teacherOptions={teacherOptions}
          loadMessageEdits={loadMessageEdits}
          back={() => setSelectedChatId(null)}
        /> : (
          <SectionPanel
            section={activeSection}
            role={role}
            chats={filteredChats}
            allChats={chats}
            lessons={lessons}
            teachers={teacherOptions}
            lessonFilter={lessonFilter}
            setLessonFilter={setLessonFilter}
            openChat={openChat}
            updateStudent={updateStudent}
            back={() => setActiveSection("chats")}
          />
        )}
      </div>
  </div>
  );
}

function ChatList({
  role,
  chats,
  allChats,
  query,
  setQuery,
  activeFilter,
  setActiveFilter,
  teacherOptions,
  teacherFilter,
  setTeacherFilter,
  activeSection,
  setActiveSection,
  selectedChatId,
  openChat,
  navSections,
  hiddenOnMobile,
}) {
  const [searchOpen, setSearchOpen] = useState(Boolean(query));
  const [filtersOpen, setFiltersOpen] = useState(false);
  const showLanguage = useMemo(() => {
    if (role === "admin") return true;
    const languages = new Set(
      (allChats || [])
        .map((chat) => String(chat.language || "").trim())
        .filter(Boolean),
    );
    return languages.size > 1;
  }, [allChats, role]);

  return (
    <aside className={[
      "flex h-full min-h-0 flex-col border-r border-zinc-200 bg-white",
      hiddenOnMobile ? "hidden md:flex" : "flex",
    ].join(" ")}>
      <div className="flex h-16 shrink-0 items-center justify-between px-5">
        <h1 className="text-2xl font-semibold tracking-normal">{role === "admin" ? "Контроль" : "Чати"}</h1>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setSearchOpen((value) => !value)}
            className="grid h-10 w-10 place-items-center rounded-full text-zinc-700 hover:bg-zinc-100"
            title="Пошук"
          >
            <Search size={21} />
          </button>
          <button
            onClick={() => setFiltersOpen((value) => !value)}
            className="grid h-10 w-10 place-items-center rounded-full text-zinc-700 hover:bg-zinc-100"
            title="Фільтри"
          >
            <SlidersHorizontal size={20} />
          </button>
        </div>
      </div>

      <div className="shrink-0 space-y-3 px-5 pb-3">
        {searchOpen && (
          <div className="flex h-11 items-center gap-2 rounded-xl bg-[#f0f2f5] px-3 text-zinc-500">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-zinc-500"
              placeholder="Пошук учня"
            />
            {query && (
              <button onClick={() => setQuery("")} className="grid h-7 w-7 place-items-center rounded-full hover:bg-white" title="Очистити">
                <X size={15} />
              </button>
            )}
          </div>
        )}
        <div className="-mx-1 overflow-x-auto pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <div className="flex min-w-max items-center gap-1.5 px-1">
            {FILTERS.map((filter) => (
              <button
                key={filter.id}
                onClick={() => setActiveFilter(filter.id)}
                className={[
                  "h-8 shrink-0 rounded-full px-2.5 text-[11px] font-semibold leading-none transition sm:px-3 sm:text-xs",
                  activeFilter === filter.id ? "bg-[#0b8fe3] text-white" : "bg-[#f4f5f7] text-zinc-700 hover:bg-zinc-200",
                ].join(" ")}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
        {role === "admin" && teacherOptions.length > 0 && filtersOpen && (
          <select
            value={teacherFilter}
            onChange={(event) => setTeacherFilter(event.target.value)}
            className="h-9 w-full rounded-lg border border-zinc-200 bg-white px-3 text-sm outline-none"
          >
            <option value="all">Усі викладачі</option>
            {teacherOptions.map((teacher) => (
              <option key={teacher.id} value={teacher.id}>{teacher.name}</option>
            ))}
          </select>
        )}
      </div>

      <div className={`min-h-0 flex-1 overflow-y-auto ${SCROLL_SAFE_AREA_CLASS}`}>
        {chats.map((chat, index) => (
          <button
            key={chat.id}
            onClick={() => {
              openChat(chat.id);
            }}
            className={[
              "relative flex w-full items-center gap-3 border-b border-zinc-100 px-5 py-3.5 text-left transition",
              selectedChatId === chat.id ? "bg-zinc-50" : "bg-white hover:bg-zinc-50",
            ].join(" ")}
          >
            <Avatar initials={chat.initials} tone={avatarTone(index, chat)} size="lg" />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="min-w-0 truncate text-[16px] font-semibold leading-5">
                    {chat.title}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-zinc-500">
                    {showLanguage && chat.language && (
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-zinc-600">
                        {languageFlag(chat.language)} {chat.language}
                      </span>
                    )}
                    {chat.level && (
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-zinc-600">
                        {chat.level}
                      </span>
                    )}
                  </div>
                </div>
                <span className="shrink-0 text-[11px] text-zinc-500">{formatTime(chat.last_message_at)}</span>
              </div>
              <p className="mt-1 text-[13px] leading-5 text-zinc-600" style={previewClamp}>
                {chat.subtitle ? (
                  <>
                    <span className="font-semibold text-[#0b8fe3]">{chatPreviewPrefix(chat, role)}:</span>{" "}
                    {chat.subtitle}
                  </>
                ) : (
                  "Повідомлень ще немає"
                )}
              </p>
              <div className="mt-0.5 flex items-start justify-between gap-2">
                <div className="flex min-w-6 shrink-0 items-center justify-end gap-1 pt-0.5">
                  {chat.possible_contact && <AlertTriangle size={15} className="text-amber-500" />}
                  {chat.unread_count > 0 && (
                    <span className="grid h-6 min-w-6 place-items-center rounded-full bg-[#0b8fe3] px-1.5 text-xs font-semibold text-white">
                      {chat.unread_count}
                    </span>
                  )}
                  {chat.unread_count === 0 && chat.last_sender === "teacher" && <span className="text-xs text-[#0b8fe3]">✓✓</span>}
                </div>
              </div>
              {chat.waiting_reply && (
                <p className="mt-1 flex items-center gap-1 text-xs font-semibold leading-4 text-amber-500">
                  <span className="h-2 w-2 rounded-full bg-amber-500" />
                  Чекає відповіді
                </p>
              )}
            </div>
          </button>
        ))}
      </div>
      <nav className={`grid h-16 border-t border-zinc-100 bg-white text-[11px] text-zinc-500 ${navSections.length === 5 ? "grid-cols-5" : "grid-cols-4"}`}>
        {navSections.map((item) => (
          <BottomNavItem
            key={item.id}
            active={activeSection === item.id}
            icon={item.icon}
            label={item.label}
            onClick={() => setActiveSection(item.id)}
          />
        ))}
      </nav>
    </aside>
  );
}

function ChatPanel({
  role,
  chat,
  messages,
  messageQuery,
  setMessageQuery,
  status,
  text,
  setText,
  sendText,
  recording,
  toggleRecording,
  deleteMessage,
  replyingTo,
  setReplyingTo,
  editingMessage,
  setEditingMessage,
  startEdit,
  fileInputRef,
  sendFiles,
  uploading,
  uploadError,
  clearUploadError,
  infoOpen,
  setInfoOpen,
  updateStudent,
  teacherOptions,
  loadMessageEdits,
  back,
}) {
  const [adminTab, setAdminTab] = useState("dialog");
  const [editHistory, setEditHistory] = useState(null);
  const messagesEndRef = useRef(null);
  const fileMessages = useMemo(() => messages.filter((message) => message.kind !== "text"), [messages]);
  const eventMessages = useMemo(() => messages.filter((message) => (
    message.possible_contact || message.is_deleted || message.edited_at
  )), [messages]);

  useEffect(() => {
    if (adminTab !== "dialog") return;
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [adminTab, chat?.id, messages.length]);

  if (!chat) {
    return (
      <section className="hidden h-full place-items-center bg-white text-sm text-zinc-500 md:grid">
        Оберіть учня
      </section>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-col bg-white">
      <header className="flex h-16 shrink-0 items-center gap-3 border-b border-zinc-200 px-3">
        <button onClick={back} className="grid h-10 w-10 place-items-center rounded-full hover:bg-zinc-100 md:hidden" title="Назад">
          <ArrowLeft size={21} />
        </button>
        <Avatar initials={chat.initials} tone="blue" size="sm" />
        <button onClick={() => setInfoOpen(true)} className="min-w-0 flex-1 text-left">
          <p className="truncate text-sm font-semibold">{chat.title}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-zinc-500">
            {chat.language && <span className="rounded-full bg-zinc-100 px-2 py-0.5">{languageFlag(chat.language)} {chat.language}</span>}
            {chat.level && <span className="rounded-full bg-zinc-100 px-2 py-0.5">{chat.level}</span>}
            <span className="rounded-full bg-zinc-100 px-2 py-0.5">{statusLabel(chat.student_status)}</span>
          </div>
        </button>
        {chat.possible_contact && <AlertTriangle size={19} className="text-amber-500" />}
        <button onClick={() => setInfoOpen(true)} className="grid h-10 w-10 place-items-center rounded-full text-zinc-600 hover:bg-zinc-100" title="Інформація">
          <Info size={20} />
        </button>
      </header>

      {role !== "admin" && <LessonGoalCard chat={chat} />}
      {infoOpen && <StudentInfo chat={chat} close={() => setInfoOpen(false)} />}

      {role === "admin" && (
        <div className="grid grid-cols-4 gap-1 border-b border-zinc-100 px-3 py-2 text-xs font-medium">
          {[
            ["dialog", "Діалог"],
            ["info", "Інформація"],
            ["files", "Файли"],
            ["events", "Журнал подій"],
          ].map(([id, label]) => (
            <button
              key={id}
              onClick={() => setAdminTab(id)}
              className={[
                "h-9 rounded-full transition",
                adminTab === id ? "bg-[#0c99c9] text-white" : "text-zinc-600 hover:bg-zinc-100",
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {role !== "admin" || adminTab === "dialog" ? <div className="border-b border-zinc-100 px-4 py-2">
        <div className="flex items-center gap-2">
          <div className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg bg-[#eef0f3] px-3 text-zinc-500">
            <Search size={16} />
            <input
              value={messageQuery}
              onChange={(event) => setMessageQuery(event.target.value)}
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
              placeholder="Пошук у чаті"
            />
          </div>
          <button
            onClick={() => downloadChatHistory(chat, messages)}
            disabled={!messages.length}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-zinc-100 text-zinc-700 hover:bg-zinc-200 disabled:opacity-40"
            title="Завантажити історію"
          >
            <Download size={17} />
          </button>
        </div>
      </div> : null}

      {role === "admin" && adminTab === "info" ? (
        <main className="flex-1 overflow-y-auto bg-white px-4 py-4">
          <LessonGoalCard chat={chat} />
          <StudentInfoContent
            chat={chat}
            editable={role === "admin"}
            teacherOptions={teacherOptions}
            onSave={(values) => updateStudent(chat.id, values)}
          />
        </main>
      ) : role === "admin" && adminTab === "files" ? (
        <main className="flex-1 overflow-y-auto bg-white px-4 py-4">
          <FileList messages={fileMessages} />
        </main>
      ) : role === "admin" && adminTab === "events" ? (
        <main className="flex-1 overflow-y-auto bg-white px-4 py-4">
          <EventLog messages={eventMessages} />
        </main>
      ) : (
        <main className={role === "admin" ? "flex-1 space-y-2 overflow-y-auto bg-[#f6f7fb] px-4 py-4" : "flex-1 space-y-2 overflow-y-auto bg-white px-4 py-4"}>
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              role={role}
              onDelete={() => deleteMessage(message.id)}
              onReply={() => {
                setEditingMessage(null);
                setReplyingTo(message);
              }}
              onEdit={() => startEdit(message)}
              onHistory={async () => {
                const edits = await loadMessageEdits(message.id);
                setEditHistory({ message, edits });
              }}
            />
          ))}
          <div ref={messagesEndRef} />
        </main>
      )}

      {editHistory && (
        <EditHistoryModal
          message={editHistory.message}
          edits={editHistory.edits}
          close={() => setEditHistory(null)}
        />
      )}

      {role !== "admin" && <footer className="shrink-0 border-t border-zinc-100 bg-white px-3 py-3">
        {(replyingTo || editingMessage) && (
          <div className="mb-2 flex items-center gap-2 rounded-lg bg-[#eef7fb] px-3 py-2 text-sm">
            {editingMessage ? <Pencil size={15} /> : <Reply size={15} />}
            <p className="min-w-0 flex-1 truncate">
              {editingMessage ? "Редагування" : `Відповідь: ${replyingTo?.text || replyingTo?.filename || "вкладення"}`}
            </p>
            <button onClick={() => {
              setReplyingTo(null);
              setEditingMessage(null);
              setText("");
            }} className="grid h-7 w-7 place-items-center rounded-full hover:bg-white" title="Скасувати">
              <X size={15} />
            </button>
          </div>
        )}
        <div className="flex items-center gap-2 rounded-full bg-[#eef0f3] px-2 py-1.5">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => sendFiles(event.target.files)}
          />
          <button
            onClick={() => {
              clearUploadError();
              fileInputRef.current?.click();
            }}
            disabled={uploading}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-zinc-500 hover:bg-white disabled:opacity-50"
            title={uploading ? "Файл завантажується" : "Додати файл"}
          >
            <Paperclip size={18} />
          </button>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") sendText();
            }}
            className="h-8 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-zinc-500"
            placeholder="Напишіть повідомлення"
          />
          <button
            onClick={toggleRecording}
            className={[
              "grid h-8 w-8 shrink-0 place-items-center rounded-full transition",
              recording ? "bg-red-100 text-red-600" : "text-zinc-500 hover:bg-white",
            ].join(" ")}
            title={recording ? "Зупинити запис" : "Голосове"}
          >
            {recording ? <Square size={15} /> : <Mic size={17} />}
          </button>
          <button
            onClick={sendText}
            disabled={!text.trim()}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#0c99c9] text-white transition hover:bg-[#087fab] disabled:bg-zinc-300"
            title="Надіслати"
          >
            {editingMessage ? <Check size={17} /> : <Send size={17} />}
          </button>
        </div>
        {(uploading || uploadError) && (
          <div className={uploadError ? "mt-2 flex items-center gap-2 text-xs text-red-600" : "mt-2 text-xs text-zinc-500"}>
            {uploadError && <AlertTriangle size={14} />}
            <span>{uploadError || "Файл завантажується..."}</span>
          </div>
        )}
      </footer>}
    </section>
  );
}

function MessageBubble({ message, role, onDelete, onReply, onEdit, onHistory }) {
  const own = message.sender_kind === "teacher" && role !== "admin";
  const adminTeacher = role === "admin" && message.sender_kind === "teacher";
  return (
    <div className={own || adminTeacher ? "flex items-end justify-end gap-2" : "flex items-end justify-start gap-2"}>
      {!own && !adminTeacher && <Avatar initials={message.sender_name?.split(" ").map((part) => part[0]).join("").slice(0, 2) || "S"} size="xs" tone="blue" />}
      <div className={[
        "group relative max-w-[78%] rounded-2xl px-3 py-2 text-sm leading-5",
        own || adminTeacher ? "rounded-br-md bg-[#0c99c9] text-white" : "rounded-bl-md bg-white text-zinc-800",
        role === "admin" && !adminTeacher ? "shadow-sm ring-1 ring-zinc-100" : "",
        message.is_deleted ? "bg-zinc-100 text-zinc-500" : "",
      ].join(" ")}>
        <div className={[
          "absolute -top-3 hidden gap-1 rounded-full bg-white p-1 shadow-sm ring-1 ring-zinc-200 group-hover:flex",
          own || adminTeacher ? "left-0 -translate-x-full" : "right-0 translate-x-full",
        ].join(" ")}>
          <IconAction icon={<Reply size={13} />} label="Відповісти" onClick={onReply} />
          {message.kind === "text" && own && !message.is_deleted && <IconAction icon={<Pencil size={13} />} label="Редагувати" onClick={onEdit} />}
          {role === "admin" && message.edited_at && <IconAction icon={<FileText size={13} />} label="Історія змін" onClick={onHistory} />}
          <IconAction icon={<Copy size={13} />} label="Копіювати" onClick={() => navigator.clipboard?.writeText(message.original_text || message.text || "")} />
          {!message.is_deleted && (own || role === "admin") && <IconAction icon={<Trash2 size={13} />} label="Видалити" onClick={onDelete} danger />}
        </div>

        {message.reply_preview && (
          <div className={own || adminTeacher ? "mb-1 border-l-2 border-white/60 pl-2 text-xs text-white/80" : "mb-1 border-l-2 border-zinc-400 pl-2 text-xs text-zinc-500"}>
            {message.reply_preview.text || mediaLabel(message.reply_preview.kind)}
          </div>
        )}
        {message.possible_contact && (
          <div className="mb-1 flex items-center gap-1 rounded-md bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700">
            <AlertTriangle size={13} /> Можливі контактні дані
          </div>
        )}
        <MessageContent message={message} role={role} />
        {role === "admin" && message.is_deleted && message.original_text && (
          <p className="mt-1 whitespace-pre-wrap break-words text-xs text-zinc-500">Оригінал: {message.original_text}</p>
        )}
        {role === "admin" && (message.is_deleted || message.edited_at) && (
          <div className={own || adminTeacher ? "mt-2 rounded-lg bg-white/15 px-2 py-1.5 text-[11px] text-white/80" : "mt-2 rounded-lg bg-white px-2 py-1.5 text-[11px] text-zinc-500"}>
            {message.is_deleted && (
              <p>
                Видалено: {message.deleted_by_name || "невідомо"}
                {message.deleted_at ? ` · ${formatDateTime(message.deleted_at)}` : ""}
              </p>
            )}
            {message.edited_at && (
              <button onClick={onHistory} className="text-left underline-offset-2 hover:underline">
                Редаговано: {message.edited_by_name || "невідомо"} · {formatDateTime(message.edited_at)}
              </button>
            )}
          </div>
        )}
        <p className={own || adminTeacher ? "mt-1 text-right text-[10px] text-white/75" : "mt-1 text-right text-[10px] text-zinc-500"}>
          {formatTime(message.created_at)}
          {message.edited_at ? " · ред." : ""}
          {message.deleted_at ? ` · видалено ${formatTime(message.deleted_at)}` : ""}
        </p>
      </div>
      {(own || adminTeacher) && <Avatar initials="T" size="xs" tone="blue" />}
    </div>
  );
}

function MessageContent({ message, role }) {
  if (message.is_deleted && role !== "admin") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed border-zinc-300 bg-white/70 px-3 py-2 text-xs text-zinc-500">
        <Trash2 size={14} />
        <span>Повідомлення видалено</span>
      </div>
    );
  }
  if (message.is_deleted && role === "admin") {
    return (
      <div className="rounded-xl bg-[#ddebfa] px-3 py-2 text-sm text-zinc-800">
        <p className="font-semibold text-[#0b5f9b]">Повідомлення видалено викладачем</p>
        <p className="mt-1 whitespace-pre-wrap break-words">
          {message.original_text || message.text || "Повідомлення видалено"}
        </p>
      </div>
    );
  }
  if (message.kind === "voice" || message.kind === "audio") {
    return <audio controls src={message.media_url || message.voice_url} className="w-56 max-w-full" />;
  }
  if (message.kind === "photo") {
    return (
      <a href={message.media_url} target="_blank" rel="noreferrer" className="block">
        <img src={message.media_url} alt={message.filename || "Фото"} className="max-h-72 rounded-lg object-contain" />
        {message.text && <p className="mt-2 whitespace-pre-wrap break-words">{message.text}</p>}
      </a>
    );
  }
  if (message.kind === "video") {
    return <video controls src={message.media_url} className="max-h-72 max-w-full rounded-lg" />;
  }
  if (message.kind !== "text") {
    const isPdf = String(message.mime_type || "").toLowerCase().includes("pdf") || /\.pdf$/i.test(message.filename || "");
    return (
      <div className="space-y-2">
        {isPdf ? (
          <object data={message.media_url} type="application/pdf" className="h-72 w-full rounded-lg border border-zinc-200 bg-white">
            <a href={message.media_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 underline-offset-2 hover:underline">
              {mediaIcon(message.kind)}
              <span className="break-all">{message.filename || mediaLabel(message.kind)}</span>
            </a>
          </object>
        ) : (
          <a href={message.media_url} target="_blank" rel="noreferrer" className="flex items-center gap-2 underline-offset-2 hover:underline">
            {mediaIcon(message.kind)}
            <span className="break-all">{message.filename || mediaLabel(message.kind)}</span>
          </a>
        )}
      </div>
    );
  }
  return <p className="whitespace-pre-wrap break-words">{message.text}</p>;
}

function StudentInfo({ chat, close }) {
  return (
    <div className="border-b border-zinc-200 bg-white px-4 py-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{chat.title}</p>
          <p className="truncate text-xs text-zinc-500">{[chat.language, chat.level].filter(Boolean).join(" · ")}</p>
        </div>
        <button onClick={close} className="grid h-8 w-8 place-items-center rounded-full hover:bg-zinc-100" title="Закрити">
          <X size={16} />
        </button>
      </div>
      <StudentInfoContent chat={chat} />
    </div>
  );
}

function StudentInfoContent({ chat, editable = false, onSave, teacherOptions = [] }) {
  const [form, setForm] = useState({
    student_status: chat.student_status || "active",
    level: chat.level || "",
    learning_format: chat.learning_format || "",
    learning_goal: chat.learning_goal || "",
    admin_note: chat.admin_note || "",
    teacher_id: chat.teacher_id ? String(chat.teacher_id) : "",
  });

  useEffect(() => {
    setForm({
      student_status: chat.student_status || "active",
      level: chat.level || "",
      learning_format: chat.learning_format || "",
      learning_goal: chat.learning_goal || "",
      admin_note: chat.admin_note || "",
      teacher_id: chat.teacher_id ? String(chat.teacher_id) : "",
    });
  }, [chat]);

  if (editable) {
    return (
      <div className="grid gap-3 text-sm">
        <label className="grid gap-1">
          <span className="text-xs text-zinc-500">Статус</span>
          <select
            value={form.student_status}
            onChange={(event) => setForm({ ...form, student_status: event.target.value })}
            className="h-10 rounded-lg border border-zinc-200 px-3 outline-none"
          >
            <option value="active">Активний</option>
            <option value="paused">Пауза</option>
            <option value="completed">Завершив навчання</option>
          </select>
        </label>
        {teacherOptions.length > 0 && (
          <label className="grid gap-1">
            <span className="text-xs text-zinc-500">Викладач</span>
            <select
              value={form.teacher_id}
              onChange={(event) => setForm({ ...form, teacher_id: event.target.value })}
              className="h-10 rounded-lg border border-zinc-200 px-3 outline-none"
            >
              <option value="">Без викладача</option>
              {teacherOptions.map((teacher) => (
                <option key={teacher.id} value={String(teacher.id)}>
                  {teacher.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField label="Рівень" value={form.level} onChange={(level) => setForm({ ...form, level })} />
          <TextField label="Формат" value={form.learning_format} onChange={(learning_format) => setForm({ ...form, learning_format })} />
        </div>
        <TextField label="Ціль навчання" value={form.learning_goal} onChange={(learning_goal) => setForm({ ...form, learning_goal })} />
        <label className="grid gap-1">
          <span className="text-xs text-zinc-500">Примітка адміністратора</span>
          <textarea
            value={form.admin_note}
            onChange={(event) => setForm({ ...form, admin_note: event.target.value })}
            className="min-h-24 rounded-lg border border-zinc-200 px-3 py-2 outline-none"
          />
        </label>
        <button
          onClick={() => onSave?.(form)}
          className="h-10 rounded-lg bg-[#0c99c9] px-4 text-sm font-semibold text-white hover:bg-[#087fab]"
        >
          Зберегти
        </button>
        <button
          onClick={() => onSave?.({ ...form, student_status: form.student_status === "completed" ? "active" : "completed" })}
          className="h-10 rounded-lg bg-zinc-100 px-4 text-sm font-semibold text-zinc-700 hover:bg-zinc-200"
        >
          {form.student_status === "completed" ? "Повернути з архіву" : "В архів"}
        </button>
      </div>
    );
  }

  const rows = [
    ["Мова", chat.language],
    ["Рівень", chat.level],
    ["Формат", chat.learning_format],
    ["Ціль", chat.learning_goal],
    ["Наступний урок", chat.next_lesson],
    ["Примітка", chat.admin_note],
    ...(chat.teacher_name ? [["Викладач", chat.teacher_name]] : []),
    ["Статус", statusLabel(chat.student_status)],
  ].filter(([, value]) => value);

  return (
    <div className="grid gap-2 text-sm text-zinc-600 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <p key={label} className="rounded-lg bg-zinc-50 px-3 py-2"><span className="text-zinc-400">{label}:</span> {value}</p>
      ))}
    </div>
  );
}

function TextField({ label, value, onChange }) {
  return (
    <label className="grid gap-1">
      <span className="text-xs text-zinc-500">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-lg border border-zinc-200 px-3 outline-none"
      />
    </label>
  );
}

function LessonGoalCard({ chat }) {
  if (!chat.next_lesson && !chat.learning_goal) return null;
  return (
    <div className="grid gap-2 border-b border-zinc-100 bg-white px-4 py-3 sm:grid-cols-2">
      <div className="flex items-center gap-3 rounded-lg border border-zinc-100 px-3 py-3">
        <CalendarDays size={19} className="text-[#0c99c9]" />
        <div className="min-w-0">
          <p className="text-xs text-zinc-500">Наступний урок</p>
          <p className="truncate text-sm font-medium">{formatDateTime(chat.next_lesson) || "Не заплановано"}</p>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-lg border border-zinc-100 px-3 py-3">
        <Target size={19} className="text-[#0c99c9]" />
        <div className="min-w-0">
          <p className="text-xs text-zinc-500">Ціль</p>
          <p className="truncate text-sm font-medium">{chat.learning_goal || "Не вказано"}</p>
        </div>
      </div>
    </div>
  );
}

function FileList({ messages }) {
  if (!messages.length) return <EmptyState text="Файлів у цьому діалозі ще немає" />;
  return (
    <div className="space-y-2">
      {messages.map((message) => (
        <a
          key={message.id}
          href={message.media_url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-3 rounded-lg border border-zinc-100 px-3 py-3 text-sm hover:bg-zinc-50"
        >
          {mediaIcon(message.kind)}
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{message.filename || mediaLabel(message.kind)}</p>
            <p className="text-xs text-zinc-500">{message.sender_name} · {formatDateTime(message.created_at)}</p>
          </div>
        </a>
      ))}
    </div>
  );
}

function EventLog({ messages }) {
  if (!messages.length) return <EmptyState text="Подій для контролю немає" />;
  return (
    <div className="space-y-2">
      {messages.map((message) => (
        <div key={message.id} className={["rounded-lg border px-3 py-3 text-sm", eventTone(message)].join(" ")}>
          <div className="flex items-center gap-2 font-semibold">
            <AlertTriangle size={16} />
            {eventTitle(message)}
          </div>
          <p className="mt-1 text-zinc-700">{message.original_text || message.text || message.filename || mediaLabel(message.kind)}</p>
          <div className="mt-1 space-y-0.5 text-xs text-zinc-500">
            <p>Автор: {message.sender_name || "Невідомо"} · {formatDateTime(message.created_at)}</p>
            {message.is_deleted && (
              <p>Видалив: {message.deleted_by_name || "невідомо"} · {formatDateTime(message.deleted_at)}</p>
            )}
            {message.edited_at && (
              <p>Редагував: {message.edited_by_name || "невідомо"} · {formatDateTime(message.edited_at)}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ text }) {
  return <div className="grid h-full place-items-center text-sm text-zinc-500">{text}</div>;
}

function ErrorPanel({ message }) {
  return (
    <section className="flex h-full min-h-0 flex-col bg-white">
      <main className="grid flex-1 place-items-center px-6 py-8">
        <div className="max-w-md rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700">
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="mt-0.5 shrink-0" />
            <div className="space-y-1">
              <p className="font-semibold">Mini App недоступна</p>
              <p>{message}</p>
            </div>
          </div>
        </div>
      </main>
    </section>
  );
}

function SectionPanel({ section, role, chats, allChats, lessons, teachers, lessonFilter, setLessonFilter, openChat, updateStudent, back }) {
  const [userView, setUserView] = useState("students");
  const [calendarDate, setCalendarDate] = useState(todayInputValue());
  const activeStudents = allChats.filter((chat) => !chat.is_archived);
  const archivedStudents = allChats.filter((chat) => chat.is_archived);
  const unreadTotal = allChats.reduce((sum, chat) => sum + (chat.unread_count || 0), 0);
  const waitingCount = allChats.filter((chat) => chat.waiting_reply).length;
  const contactCount = allChats.filter((chat) => chat.possible_contact).length;
  const visibleLessons = lessons.filter((lesson) => lessonMatchesFilter(lesson, lessonFilter, calendarDate));
  const assignedTeacherCount = new Set(allChats.map((chat) => chat.teacher_id).filter(Boolean)).size;

  if (section === "students") {
    const showStudents = userView === "students" || userView === "all";
    const showTeachers = role === "admin" && (userView === "teachers" || userView === "all");
    return (
      <section className="flex h-full min-h-0 flex-col bg-white">
        <PanelHeader
          title={role === "admin" ? "Користувачі" : "Учні"}
          subtitle={role === "admin" ? `${activeStudents.length} активних · ${teachers.length} викладачів` : `${activeStudents.length} активних · ${archivedStudents.length} в архіві`}
          back={back}
        />
        <main className={`flex-1 overflow-y-auto px-4 py-4 ${role === "admin" ? SCROLL_SAFE_AREA_CLASS : ""}`}>
          {role === "admin" && (
            <div className="mb-3 grid grid-cols-3 gap-1 rounded-lg bg-zinc-100 p-1 text-xs font-semibold">
              {[
                ["students", "Учні"],
                ["teachers", "Викладачі"],
                ["all", "Усі"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setUserView(id)}
                  className={["h-8 rounded-md", userView === id ? "bg-white text-[#0c99c9] shadow-sm" : "text-zinc-600"].join(" ")}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          <div className="grid gap-3">
            {showStudents && (
              <div className="grid gap-2">
                {role === "admin" && <p className="text-xs font-semibold uppercase text-zinc-400">Учні</p>}
                {allChats.map((chat) => (
                  <div key={chat.id} className="rounded-lg border border-zinc-100 px-3 py-3">
                    <div className="flex items-center gap-3">
                      <Avatar initials={chat.initials} size="sm" tone={chat.is_archived ? "yellow" : "blue"} />
                      <button onClick={() => openChat(chat.id)} className="min-w-0 flex-1 text-left">
                        <p className="truncate text-sm font-semibold">{chat.title}</p>
                        <p className="truncate text-xs text-zinc-500">{[chat.language, chat.level, chat.teacher_name || "без викладача", statusLabel(chat.student_status)].filter(Boolean).join(" · ")}</p>
                      </button>
                      {chat.waiting_reply && <span className="rounded-full bg-amber-100 px-2 py-1 text-[11px] font-semibold text-amber-700">Відповісти</span>}
                    </div>
                    {role === "admin" && (
                      <div className="mt-3 grid grid-cols-3 gap-0.5">
                        {[
                          ["active", "Активний", "Актив."],
                          ["paused", "Пауза", "Пауза"],
                          ["completed", "Завершив", "Архів"],
                        ].map(([value, label, mobileLabel]) => (
                          <button
                            key={value}
                            onClick={() => updateStudent(chat.id, { student_status: value })}
                            className={[
                              "h-6 min-w-0 rounded-md px-0.5 text-[10px] font-medium leading-none tracking-normal",
                              chat.student_status === value ? "bg-[#0c99c9] text-white" : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200",
                            ].join(" ")}
                          >
                            <span className="sm:hidden">{mobileLabel}</span>
                            <span className="hidden sm:inline">{label}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {showTeachers && (
              <div className="grid gap-2">
                <p className="text-xs font-semibold uppercase text-zinc-400">Викладачі</p>
                {teachers.map((teacher) => {
                  const teacherStudents = allChats.filter((chat) => String(chat.teacher_id || "") === String(teacher.id));
                  return (
                    <div key={teacher.id} className="rounded-lg border border-zinc-100 px-3 py-3">
                      <p className="truncate text-sm font-semibold">{teacher.name}</p>
                      <p className="mt-1 text-xs text-zinc-500">{teacherStudents.length} учнів · {teacherStudents.filter((chat) => chat.waiting_reply).length} чекають відповіді</p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </main>
      </section>
    );
  }

  if (section === "lessons") {
    return (
      <section className="flex h-full min-h-0 flex-col bg-white">
        <PanelHeader title="Уроки" subtitle={`${visibleLessons.length} з ${lessons.length} заплановано`} back={back} />
        <main className={`flex-1 overflow-y-auto px-4 py-4 ${role === "admin" ? SCROLL_SAFE_AREA_CLASS : ""}`}>
          <div className="mb-3 flex gap-1 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {LESSON_FILTERS.map((filter) => (
              <button
                key={filter.id}
                onClick={() => setLessonFilter(filter.id)}
                className={[
                  "h-8 shrink-0 rounded-full px-3 text-xs font-semibold",
                  lessonFilter === filter.id ? "bg-[#0c99c9] text-white" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200",
                ].join(" ")}
              >
                {filter.label}
              </button>
            ))}
          </div>
          {lessonFilter === "calendar" && (
            <label className="mb-3 grid gap-1 text-xs text-zinc-500">
              Дата
              <input
                type="date"
                value={calendarDate}
                onChange={(event) => setCalendarDate(event.target.value)}
                className="h-10 rounded-lg border border-zinc-200 px-3 text-sm text-zinc-800 outline-none"
              />
            </label>
          )}
          {!visibleLessons.length ? <EmptyState text="Запланованих уроків за цим фільтром не знайдено" /> : (
            <div className="space-y-2">
              {visibleLessons.map((lesson) => {
                const content = (
                  <>
                  <CalendarDays size={20} className="text-[#0c99c9]" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{lesson.title}</p>
                    <p className="text-xs text-zinc-500">{formatDateTime(lesson.scheduled_at)}{role === "admin" && lesson.teacher_name ? ` · ${lesson.teacher_name}` : ""}</p>
                  </div>
                  <span className="min-w-0 max-w-[42%] shrink text-right text-xs leading-4 text-zinc-500 break-words">
                    {lesson.kind === "group" ? (lesson.participants || "Група") : (lesson.student_name || "Індивідуально")}
                  </span>
                  </>
                );
                if (lesson.chat_id) {
                  return (
                    <button
                      key={lesson.id}
                      onClick={() => openChat(lesson.chat_id)}
                      className="flex w-full items-start gap-3 rounded-lg border border-zinc-100 px-3 py-3 text-left hover:bg-zinc-50"
                    >
                      {content}
                    </button>
                  );
                }
                return (
                  <div
                    key={lesson.id}
                    className="flex w-full items-start gap-3 rounded-lg border border-zinc-100 px-3 py-3 text-left"
                  >
                    {content}
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </section>
    );
  }

  return (
    <section className="flex h-full min-h-0 flex-col bg-white">
      <PanelHeader title={role === "admin" ? "Звіти" : "Статистика"} subtitle={role === "admin" ? "Адміністратор" : "Викладач"} back={back} />
      <main className={`grid flex-1 content-start gap-3 overflow-y-auto px-4 py-4 ${role === "admin" ? SCROLL_SAFE_AREA_CLASS : ""}`}>
        <SummaryCard label="Активні учні" value={activeStudents.length} />
        <SummaryCard label="Непрочитані" value={unreadTotal} />
        <SummaryCard label="Чекають відповіді" value={waitingCount} />
        <SummaryCard label="Заплановано уроків" value={lessons.length} />
        <SummaryCard label="Архів" value={archivedStudents.length} />
        {role === "admin" && <SummaryCard label="Викладачів з учнями" value={assignedTeacherCount} />}
        {role === "admin" && <SummaryCard label="Усього викладачів" value={teachers.length} />}
        {role === "admin" && <SummaryCard label="Контактні попередження" value={contactCount} />}
      </main>
    </section>
  );
}

async function readApiError(response, fallbackMessage) {
  try {
    const payload = await response.json();
    if (payload?.error) return payload.error;
  } catch {
    // ignore malformed error payloads
  }
  if (response.status === 401) return "Потрібна повторна авторизація в Telegram";
  if (response.status === 403) return "Немає доступу до Mini App для цього акаунта";
  return fallbackMessage;
}

function getStoredAdminSection() {
  const value = window.localStorage.getItem(ADMIN_SECTION_STORAGE_KEY);
  return isAdminSection(value) ? value : "admin";
}

function isAdminSection(value) {
  return ["admin", "chats", "students", "lessons", "profile"].includes(value);
}

function AdminPanel({ role, chats, allChats, teachers, openChat, setActiveSection, setTeacherFilter, setActiveFilter, back }) {
  const unreadChats = allChats.filter((chat) => (chat.unread_count || 0) > 0);
  const waitingChats = allChats.filter((chat) => chat.waiting_reply);
  const contactChats = allChats.filter((chat) => chat.possible_contact);
  const archivedChats = allChats.filter((chat) => chat.is_archived);
  const recentPriority = [...allChats]
    .filter((chat) => chat.waiting_reply || chat.possible_contact || (chat.unread_count || 0) > 0)
    .sort((a, b) => {
      const score = (chat) => {
        let value = 0;
        if (chat.possible_contact) value += 4;
        if (chat.waiting_reply) value += 2;
        value += Math.min(chat.unread_count || 0, 3);
        return value;
      };
      return score(b) - score(a);
    })
    .slice(0, 8);

  return (
    <section className="flex h-full min-h-0 flex-col bg-white">
      <PanelHeader title="Адмін" subtitle={role === "admin" ? "Керування workspace" : "Доступ обмежено"} back={back} />
      <main className={`min-h-0 flex-1 overflow-y-auto bg-[#f6f7fb] px-4 py-4 ${SCROLL_SAFE_AREA_CLASS}`}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <SummaryCard label="Усього чатів" value={allChats.length} />
          <SummaryCard label="Непрочитані" value={unreadChats.length} />
          <SummaryCard label="Чекають відповіді" value={waitingChats.length} />
          <SummaryCard label="Контактні попередження" value={contactChats.length} />
          <SummaryCard label="В архіві" value={archivedChats.length} />
          <SummaryCard label="Викладачів" value={teachers.length} />
        </div>

        <div className="mt-4 rounded-lg border border-zinc-100 bg-white px-4 py-4">
          <p className="text-sm font-semibold text-zinc-800">Швидкі переходи</p>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ["chats", "Чати"],
              ["students", "Користувачі"],
              ["lessons", "Уроки"],
              ["profile", "Звіти"],
            ].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setActiveSection(id)}
                className="h-10 rounded-lg bg-zinc-100 px-3 text-sm font-semibold text-zinc-700 hover:bg-zinc-200"
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-zinc-100 bg-white px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-zinc-800">Переписки по викладачу</p>
            <span className="text-xs text-zinc-500">{teachers.length}</span>
          </div>
          <div className="mt-3 grid gap-2">
            {teachers.map((teacher) => {
              const teacherChats = allChats.filter((chat) => String(chat.teacher_id || "") === String(teacher.id));
              return (
                <button
                  key={teacher.id}
                  onClick={() => {
                    setTeacherFilter(String(teacher.id));
                    setActiveFilter("all");
                    setActiveSection("chats");
                  }}
                  className="flex h-10 items-center justify-between gap-3 rounded-lg bg-zinc-100 px-3 text-left text-sm font-semibold text-zinc-700 hover:bg-zinc-200"
                >
                  <span className="truncate">{teacher.name}</span>
                  <span className="shrink-0 text-xs text-zinc-500">{teacherChats.length}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-zinc-100 bg-white px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-zinc-800">Пріоритетні чати</p>
              <p className="text-xs text-zinc-500">Непрочитані, з очікуванням відповіді або з контактними даними</p>
            </div>
            <span className="text-xs text-zinc-500">{recentPriority.length} з {allChats.length}</span>
          </div>

          <div className="mt-3 space-y-2">
            {recentPriority.length ? recentPriority.map((chat) => (
              <button
                key={chat.id}
                onClick={() => openChat(chat.id)}
                className="flex w-full items-center justify-between gap-3 rounded-lg border border-zinc-100 px-3 py-3 text-left hover:bg-zinc-50"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-zinc-900">{chat.title}</p>
                  <p className="truncate text-xs text-zinc-500">
                    {[chat.language, chat.level, chat.teacher_name].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-xs font-semibold">
                  {chat.possible_contact && <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-700">Контакт</span>}
                  {chat.waiting_reply && <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-700">Відповісти</span>}
                  {(chat.unread_count || 0) > 0 && <span className="rounded-full bg-[#0c99c9] px-2 py-1 text-white">{chat.unread_count}</span>}
                </div>
              </button>
            )) : (
              <EmptyState text="Поки що немає пріоритетних чатів" />
            )}
          </div>
        </div>
      </main>
    </section>
  );
}

function PanelHeader({ title, subtitle, back }) {
  return (
    <header className="flex h-16 shrink-0 items-center gap-3 border-b border-zinc-200 px-4">
      {back && (
        <button onClick={back} className="grid h-10 w-10 place-items-center rounded-full hover:bg-zinc-100 md:hidden" title="До чатів">
          <ArrowLeft size={21} />
        </button>
      )}
      <div className="min-w-0">
        <h2 className="truncate text-lg font-semibold">{title}</h2>
        <p className="truncate text-xs text-zinc-500">{subtitle}</p>
      </div>
    </header>
  );
}

function SummaryCard({ label, value }) {
  return (
    <div className="rounded-lg border border-zinc-100 px-4 py-3">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function EditHistoryModal({ message, edits, close }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4">
      <div className="max-h-[80vh] w-full max-w-lg overflow-hidden rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3">
          <p className="text-sm font-semibold">Історія редагувань</p>
          <button onClick={close} className="grid h-8 w-8 place-items-center rounded-full hover:bg-zinc-100" title="Закрити">
            <X size={16} />
          </button>
        </div>
        <div className="max-h-[60vh] space-y-3 overflow-y-auto px-4 py-4 text-sm">
          {!edits.length ? (
            <p className="text-zinc-500">Історії змін немає.</p>
          ) : edits.map((edit) => (
            <div key={edit.id} className="rounded-lg border border-zinc-100 px-3 py-3">
              <p className="text-xs text-zinc-500">{edit.edited_by_name || "Невідомо"} · {formatDateTime(edit.edited_at)}</p>
              <p className="mt-2 text-xs font-semibold text-zinc-500">Було</p>
              <p className="whitespace-pre-wrap break-words">{edit.previous_text}</p>
              <p className="mt-2 text-xs font-semibold text-zinc-500">Стало</p>
              <p className="whitespace-pre-wrap break-words">{edit.new_text}</p>
            </div>
          ))}
          <p className="text-xs text-zinc-400">Поточне повідомлення ID: {message.id}</p>
        </div>
      </div>
    </div>
  );
}

function BottomNavItem({ icon, label, active = false, onClick }) {
  return (
    <button onClick={onClick} className={["flex flex-col items-center justify-center gap-1", active ? "text-[#0c99c9]" : "text-zinc-500"].join(" ")}>
      {icon}
      <span>{label}</span>
    </button>
  );
}

function MessageIcon() {
  return <span className="grid h-[18px] w-[18px] place-items-center rounded-full bg-current text-[10px] text-white" />;
}

function IconAction({ icon, label, onClick, danger = false }) {
  return (
    <button
      onClick={onClick}
      className={["grid h-7 w-7 place-items-center rounded-full hover:bg-zinc-100", danger ? "text-red-600" : "text-zinc-600"].join(" ")}
      title={label}
    >
      {icon}
    </button>
  );
}

function Avatar({ initials, tone = "blue", size = "md" }) {
  const sizes = {
    xs: "h-7 w-7 text-[11px]",
    sm: "h-10 w-10 text-sm",
    md: "h-12 w-12 text-sm",
    lg: "h-14 w-14 text-lg",
  };
  const tones = {
    blue: "bg-[#0c99c9] text-white",
    yellow: "bg-[#ffc400] text-white",
    violet: "bg-[#6f63f6] text-white",
    green: "bg-[#35c783] text-white",
    cyan: "bg-[#45c6cf] text-white",
  };
  return (
    <div className={`grid shrink-0 place-items-center rounded-full font-semibold ${sizes[size]} ${tones[tone]}`}>
      {initials}
    </div>
  );
}

function upsertMessage(messages, message) {
  if (!message) return messages;
  const found = messages.some((item) => item.id === message.id);
  if (!found) return [...messages, message];
  return messages.map((item) => (item.id === message.id ? message : item));
}

function markMessageDeletedLocally(messages, messageId) {
  let chatId = null;
  const next = messages.map((message) => {
    if (String(message.id) !== String(messageId)) return message;
    chatId = message.chat_id;
    return { ...message, is_deleted: true, text: "Повідомлення видалено" };
  });
  return { messages: next, chatId };
}

function syncChatFromMessages(chats, chatId, messages, options = {}) {
  const { unreadDelta = 0, clearUnread = false } = options;
  const chatMessages = messages
    .filter((message) => String(message.chat_id) === String(chatId) && !message.is_deleted)
    .sort(compareMessages);
  const lastMessage = chatMessages.at(-1);

  const next = chats.map((chat) => {
    if (String(chat.id) !== String(chatId)) return chat;
    if (!lastMessage) {
      return {
        ...chat,
        subtitle: "",
        last_sender: "",
        waiting_reply: false,
        last_message_at: "",
      };
    }
    const fromStudent = lastMessage.sender_kind === "student";
    return {
      ...chat,
      subtitle: lastMessage.kind === "text" ? lastMessage.text : mediaLabel(lastMessage.kind),
      last_sender: lastMessage.sender_kind,
      waiting_reply: fromStudent,
      last_message_at: lastMessage.created_at,
      unread_count: clearUnread ? 0 : Math.max(0, (chat.unread_count || 0) + unreadDelta),
      possible_contact: chat.possible_contact || lastMessage.possible_contact,
    };
  });
  return next.sort((a, b) => String(b.last_message_at).localeCompare(String(a.last_message_at)));
}

function compareMessages(a, b) {
  const timeCompare = String(a.created_at || "").localeCompare(String(b.created_at || ""));
  if (timeCompare !== 0) return timeCompare;
  return Number(a.id || 0) - Number(b.id || 0);
}

function downloadChatHistory(chat, messages) {
  const lines = [
    `Історія переписки: ${chat?.title || "Чат"}`,
    `Експорт: ${new Date().toLocaleString()}`,
    "",
    ...[...messages].sort(compareMessages).map((message) => {
      const sender = message.sender_name || (message.sender_kind === "teacher" ? "Викладач" : "Учень");
      const body = message.original_text || message.text || message.filename || mediaLabel(message.kind);
      const flags = [
        message.is_deleted ? "видалено" : "",
        message.edited_at ? "редаговано" : "",
        message.possible_contact ? "можливі контакти" : "",
      ].filter(Boolean);
      return `[${formatDateTime(message.created_at)}] ${sender}: ${body}${flags.length ? ` (${flags.join(", ")})` : ""}`;
    }),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `chat-${chat?.id || "history"}.txt`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function mediaLabel(kind) {
  return {
    photo: "Фото",
    video: "Відео",
    document: "Документ",
    audio: "Аудіо",
    voice: "Голосове",
  }[kind] || "Вкладення";
}

function mediaIcon(kind) {
  if (kind === "photo") return <Image size={18} />;
  if (kind === "video") return <Video size={18} />;
  if (kind === "audio" || kind === "voice") return <Music size={18} />;
  return <FileText size={18} />;
}

function statusLabel(status) {
  return {
    active: "Активний",
    paused: "Пауза",
    completed: "Завершив навчання",
  }[status] || status;
}

function lessonMatchesFilter(lesson, filter, calendarDate) {
  if (filter === "all") return true;
  const date = parseLocalDate(lesson.scheduled_at);
  if (!date) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const lessonDay = new Date(date);
  lessonDay.setHours(0, 0, 0, 0);
  if (filter === "today") {
    return lessonDay.getTime() === today.getTime();
  }
  const weekEnd = new Date(today);
  weekEnd.setDate(today.getDate() + 7);
  if (filter === "week") {
    return lessonDay >= today && lessonDay < weekEnd;
  }
  if (filter === "calendar") {
    const selected = parseLocalDate(calendarDate);
    if (!selected) return false;
    selected.setHours(0, 0, 0, 0);
    return lessonDay.getTime() === selected.getTime();
  }
  return true;
}

function parseLocalDate(value) {
  if (!value) return null;
  const date = new Date(String(value).replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function todayInputValue() {
  const date = new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const previewClamp = {
  display: "-webkit-box",
  WebkitBoxOrient: "vertical",
  WebkitLineClamp: 2,
  overflow: "hidden",
};

function chatPreviewPrefix(chat, role) {
  if (chat.last_sender === "teacher") {
    return role === "admin" ? "Викладач" : "Ви";
  }
  return "Учень";
}

function avatarTone(index, chat) {
  return ["blue", "violet", "green", "yellow", "cyan"][index % 5];
}

function firstName(value) {
  return String(value || "Учень").trim().split(/\s+/)[0] || "Учень";
}

function languageFlag(language) {
  const value = String(language || "").toLowerCase();
  if (value.includes("англ") || value.includes("english")) return "🇬🇧";
  if (value.includes("нім") || value.includes("german")) return "🇩🇪";
  if (value.includes("поль") || value.includes("polish")) return "🇵🇱";
  if (value.includes("фран") || value.includes("french")) return "🇫🇷";
  if (value.includes("ісп") || value.includes("spanish")) return "🇪🇸";
  if (value.includes("слова") || value.includes("slovak")) return "🇸🇰";
  return "";
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function eventTitle(message) {
  if (message.possible_contact) return "Можлива передача контактних даних";
  if (message.is_deleted) return "Повідомлення видалено";
  if (message.edited_at) return "Повідомлення редаговано";
  return "Подія";
}

function eventTone(message) {
  if (message.possible_contact) return "border-amber-100 bg-amber-50 text-amber-700";
  if (message.is_deleted) return "border-red-100 bg-red-50 text-red-700";
  if (message.edited_at) return "border-blue-100 bg-blue-50 text-blue-700";
  return "border-zinc-100 bg-zinc-50 text-zinc-700";
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function chatIdFromStartParam(value) {
  const match = String(value || "").match(/chat_(\d+)/);
  return match ? Number(match[1]) : null;
}
