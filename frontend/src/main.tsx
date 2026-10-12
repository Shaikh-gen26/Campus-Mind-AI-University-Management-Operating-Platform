import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  Bell,
  BookOpen,
  BotIcon,
  CalendarClockIcon,
  CalendarDays,
  ChartNoAxesCombined,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  ClipboardListIcon,
  FileTextIcon,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  MegaphoneIcon,
  MessageCircle,
  Plus,
  Search,
  ShieldCheck,
  UserRoundIcon,
  Users,
  X,
} from 'lucide-react';
import './style.css';


if (typeof window !== 'undefined') {
  try {
    window.localStorage.removeItem('campus_token');
  } catch {
    // Authentication no longer depends on browser storage.
  }
}

const API = import.meta.env.VITE_API_URL || '/api';
type User = {
  id: number;
  login: string;
  full_name: string;
  email: string;
  role: string;
  course_id: number | null;
  student_id: number | null;
};
type Field = {
  name: string;
  label: string;
  type?: string;
  required?: boolean;
  options?: { value: string; label: string }[];
  defaultValue?: string;
};
type Action = {
  label: string;
  path: string;
  fields: Field[];
  method?: 'POST' | 'PATCH';
  body?: (values: Record<string, string>) => Record<string, unknown>;
};
const icons: Record<string, React.ReactNode> = {
  Overview: <LayoutDashboard />,
  Profile: <UserRoundIcon />,
  Students: <Users />,
  Courses: <GraduationCap />,
  Subjects: <BookOpen />,
  Attendance: <ClipboardCheck />,
  Assignments: <ClipboardListIcon />,
  Submissions: <Check />,
  Grades: <ChartNoAxesCombined />,
  Timetable: <CalendarDays />,
  Exams: <FileTextIcon />,
  Announcements: <MegaphoneIcon />,
  Events: <CalendarClockIcon />,
  Notifications: <Bell />,
  FAQs: <CircleHelp />,
  Administrators: <ShieldCheck />,
  Analytics: <Activity />,
  
  'My Campus-Intelligent': <BotIcon />,
};

async function api(path: string, _token: string, init: RequestInit = {}) {
  const response = await fetch(`${API}${path}`, {
    ...init,
    credentials: 'include',
    headers: { ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}
const paths: Record<string, string> = {
  Overview: '/dashboard',
  Profile: '/auth/me',
  Students: '/students',
  Courses: '/courses',
  Subjects: '/subjects',
  Attendance: '/attendance',
  Assignments: '/assignments',
  Submissions: '/submissions',
  Grades: '/grades',
  Timetable: '/timetable',
  Exams: '/exams',
  Announcements: '/announcements',
  Events: '/events',
  Notifications: '/notifications',
  FAQs: '/faqs',
  Administrators: '/administrators',
  Analytics: '/analytics/overview',
};
const pretty = (v: unknown) =>
  typeof v === 'boolean'
    ? v
      ? 'Yes'
      : 'No'
    : v === null || v === undefined
      ? '—'
      : typeof v === 'object'
        ? new Date(String(v)).toLocaleString()
        : String(v);

function IntelligenceBar({
  label,
  value,
  suffix = '%',
}: {
  label: string;
  value: number;
  suffix?: string;
}) {
  const safeValue = Math.max(0, Math.min(100, Number(value) || 0));

  return (
    <div className="intelligence-bar-row">
      <div className="intelligence-bar-label">
        <span>{label}</span>
        <b>
          {Number(value || 0).toFixed(1)}
          {suffix}
        </b>
      </div>

      <div className="intelligence-bar-track">
        <div
          className="intelligence-bar-fill"
          style={{ width: `${safeValue}%` }}
        />
      </div>
    </div>
  );
}


function App() {
  const [token, setToken] = useState('session-check');
  const [user, setUser] = useState<User | null>(null);
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [page, setPage] = useState('Overview');
  const [data, setData] = useState<any>(null);
  const [intelligence, setIntelligence] = useState<any>(null);
  const [riskIntelligence, setRiskIntelligence] = useState<any>(null);
  const [booting, setBooting] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [studentOffset, setStudentOffset] = useState(0);
  const [faqCategory, setFaqCategory] = useState('');
  const [modal, setModal] = useState<Action | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState('');
  const [question, setQuestion] = useState('');
  const [kind, setKind] = useState('campus');
  const [answer, setAnswer] = useState('');
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [chatMessages, setChatMessages] = useState<any[]>([]);
  const [chatHistory, setChatHistory] = useState<any[]>([]);
  const [chatSources, setChatSources] = useState<any[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [courseRows, setCourseRows] = useState<any[]>([]);
  const [subjectRows, setSubjectRows] = useState<any[]>([]);
  const [studentRows, setStudentRows] = useState<any[]>([]);
  const [categoryRows, setCategoryRows] = useState<any[]>([]);

  const reload = useCallback(async () => {
    if (!token || !user) return;
    setBusy(true);
    setError('');
    try {
      const path = paths[page] || '/dashboard';
      const suffix =
        page === 'Students'
          ? `?search=${encodeURIComponent(search)}&limit=100&offset=${studentOffset}`
          : page === 'FAQs'
            ? `?query=${encodeURIComponent(search)}${faqCategory ? `&category_id=${faqCategory}` : ''}`
            : '';
      const result = await api(path + suffix, token);
      setData(result);

      if (page === 'Overview') {
        const intelligenceResult = await api('/intelligence/overview', token);
        setIntelligence(intelligenceResult);

        const riskResult = await api('/intelligence/risk', token);
          setRiskIntelligence(riskResult);  
      }

      if (page === 'Overview') {
        const extras =
          user.role === 'super_admin'
            ? ['/courses', '/events']
            : user.role === 'course_admin'
              ? ['/courses', '/announcements']
              : ['/timetable', '/notifications'];
        await Promise.all(extras.map((p) => api(p, token).catch(() => null)));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [token, user, page, search, studentOffset, faqCategory]);
  useEffect(() => {
    let live = true;
    if (!token) {
      setBooting(false);
      return;
    }
    api('/auth/me', token)
      .then((u: User) => {
        if (live) setUser(u);
      })
      .catch(() => {
        setToken('');
      })
      .finally(() => {
        if (live) setBooting(false);
      });
    return () => {
      live = false;
    };
  }, [token]);
  useEffect(() => {
    reload();
  }, [reload]);
  useEffect(() => {
    if (token)
      api('/notifications/unread-count', token)
        .then((x: any) => setUnreadCount(x.unread))
        .catch(() => setUnreadCount(0));
  }, [token, page, data]);
  useEffect(() => {
    if (!token || !['My Campus-Intelligent'].includes(page)) return;
    const mode = page === 'My Campus-Intelligent' ? 'academic': 'campus';
    setKind(mode);
    api('/conversations', token)
      .then((all: any[]) => setChatHistory(all.filter((c) => c.kind === mode)))
      .catch(() => setChatHistory([]));
  }, [token, page]);
  async function loadLookups() {
    if (!token || !user) return;
    const studentLookup =
      user.role === 'super_admin'
        ? Promise.all(
            [0, 100, 200, 300].map((offset) =>
              api(`/students?limit=100&offset=${offset}`, token).catch(() => [])
            )
          ).then((parts) => parts.flat())
        : api('/students?limit=100', token).catch(() => []);
    const [c, s, st, cat] = await Promise.all([
      api('/courses', token).catch(() => []),
      api('/subjects', token).catch(() => []),
      studentLookup,
      api('/faq-categories', token).catch(() => []),
    ]);
    setCourseRows(c);
    setSubjectRows(s);
    setStudentRows(st);
    setCategoryRows(cat);
  }
  useEffect(() => {
    loadLookups();
  }, [token, user]);
  const rolePages = useMemo(
    () =>
      user?.role === 'student'
        ? [
            'Overview',
            'Profile',
            'Timetable',
            'Attendance',
            'Assignments',
            'Grades',
            'Exams',
            'Announcements',
            'Events',
            'Notifications',
            'FAQs',
            
            'My Campus-Intelligent',
          ]
        : user?.role === 'course_admin'
          ? [
              'Overview',
              'Profile',
              'Students',
              'Courses',
              'Subjects',
              'Attendance',
              'Assignments',
              'Submissions',
              'Grades',
              'Timetable',
              'Exams',
              'Announcements',
              'Notifications',
              'FAQs',
              
              'My Campus-Intelligent',
            ]
          : [
              'Overview',
              'Profile',
              'Students',
              'Administrators',
              'Courses',
              'Subjects',
              'Attendance',
              'Assignments',
              'Submissions',
              'Grades',
              'Timetable',
              'Exams',
              'Announcements',
              'Events',
              'Notifications',
              'FAQs',
              'Analytics',
              
              'My Campus-Intelligent',
            ],
    [user]
  );
  const isAdmin = user?.role === 'super_admin';
  const isStaff = user?.role === 'course_admin' || isAdmin;
  async function signIn(e: FormEvent) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const response = await fetch(`${API}/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: login, password }),
      });
      const body = await response.json();
      if (!response.ok) throw Error(body.detail || 'Sign in failed');
      setUser(body.user);
      setToken('authenticated');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    try {
      await api('/auth/logout', token, { method: 'POST' });
    } catch {}
    setToken('');
    setUser(null);
    setData(null);
    setPage('Overview');
  }

  const actionFor = (name: string): Action | null => {
    const courseOptions = courseRows.map((x) => ({
      value: String(x.id),
      label: `${x.code} — ${x.name}`,
    }));
    const subjectOptions = subjectRows.map((x) => ({
      value: String(x.id),
      label: `${x.code} — ${x.name}`,
    }));
    const studentOptions = studentRows.map((x) => ({
      value: String(x.id),
      label: `${x.student_number} — ${x.full_name}`,
    }));
    const categoryOptions = categoryRows.map((x) => ({ value: String(x.id), label: x.name }));
    const select = (name: string, label: string, options: Field['options']): Field => ({
      name,
      label,
      type: 'select',
      required: true,
      options,
    });
    const text = (name: string, label: string, type = 'text', required = true): Field => ({
      name,
      label,
      type,
      required,
    });
    if (name === 'Profile')
      return {
        label: 'Update profile',
        path: '/profile',
        method: 'PATCH',
        fields: [text('full_name', 'Full name'), text('email', 'Email', 'email')],
      };
    if (name === 'Students' && isAdmin)
      return {
        label: 'Add student',
        path: '/students',
        fields: [
          text('student_number', 'Student ID'),
          text('full_name', 'Full name'),
          text('email', 'Email', 'email'),
          select('course_id', 'Course', courseOptions),
          text('year', 'Year', 'number'),
          text('password', 'Temporary password', 'password'),
        ],
      };




    if (name === 'Administrators' && isAdmin)
      return {
        label: 'Add course administrator',
        path: '/administrators',
        fields: [
          text('login', 'Login ID'),
          text('full_name', 'Full name'),
          text('email', 'Email', 'email'),
          select('course_id', 'Assigned course', courseOptions),
          select('subject_1_id', 'Subject 1', subjectOptions),
          select('subject_2_id', 'Subject 2', subjectOptions),
          text('password', 'Temporary password', 'password'),
        ],
        body: (values) => ({
          login: values.login,
          full_name: values.full_name,
          email: values.email,
          password: values.password,
          course_id: Number(values.course_id),
          subject_ids: [
            Number(values.subject_1_id),
            Number(values.subject_2_id),
          ],
        }),
      };





    if (name === 'Courses' && isAdmin)
      return {
        label: 'Add course',
        path: '/courses',
        fields: [text('code', 'Course code'), text('name', 'Course name')],
      };
    if (name === 'Subjects' && isAdmin)
      return {
        label: 'Add subject',
        path: '/subjects',
        fields: [
          text('code', 'Subject code'),
          text('name', 'Subject name'),
          select('course_id', 'Course', courseOptions),
        ],
      };
    if (name === 'Attendance' && isStaff)
      return {
        label: 'Mark attendance',
        path: '/attendance',
        fields: [
          select('subject_id', 'Subject', subjectOptions),
          select('student_id', 'Student', studentOptions),
          text('held_on', 'Class date', 'date'),
          {
            name: 'present',
            label: 'Attendance status',
            type: 'select',
            required: true,
            options: [
              { value: 'true', label: 'Present' },
              { value: 'false', label: 'Absent' },
            ],
          },
        ],
      };
    if (name === 'Assignments' && isStaff)
      return {
        label: 'Create assignment',
        path: '/assignments',
        fields: [
          select('subject_id', 'Subject', subjectOptions),
          text('title', 'Title'),
          text('description', 'Instructions', 'textarea'),
          text('due_at', 'Due date', 'datetime-local'),
          text('max_score', 'Maximum marks', 'number'),
          {
            name: 'published',
            label: 'Publish now',
            type: 'select',
            required: true,
            options: [
              { value: 'true', label: 'Published' },
              { value: 'false', label: 'Draft' },
            ],
          },
        ],
      };
    if (name === 'Grades' && isStaff)
      return {
        label: 'Record grade',
        path: '/grades',
        fields: [
          select('student_id', 'Student', studentOptions),
          select('subject_id', 'Subject', subjectOptions),
          text('assessment', 'Assessment'),
          text('score', 'Score', 'number'),
          text('max_score', 'Maximum score', 'number'),
          {
            name: 'published',
            label: 'Publish result',
            type: 'select',
            required: true,
            options: [
              { value: 'true', label: 'Published' },
              { value: 'false', label: 'Draft' },
            ],
          },
        ],
      };
    if (name === 'Announcements' && isStaff)
      return {
        label: 'Publish announcement',
        path: '/announcements',
        fields: [
          text('title', 'Title'),
          text('body', 'Announcement', 'textarea'),
          ...(isAdmin
            ? [
                {
                  ...select('course_id', 'Course (blank means university-wide)', [
                    { value: '', label: 'University-wide' },
                    ...courseOptions,
                  ]),
                  required: false,
                },
              ]
            : []),
          {
            name: 'published',
            label: 'Publish now',
            type: 'select',
            required: true,
            options: [
              { value: 'true', label: 'Published' },
              { value: 'false', label: 'Draft' },
            ],
          },
        ],
      };
    if (name === 'Events' && isAdmin)
      return {
        label: 'Create event',
        path: '/events',
        fields: [
          text('title', 'Event title'),
          text('description', 'Description', 'textarea', false),
          text('starts_at', 'Date and time', 'datetime-local'),
          text('location', 'Location'),
        ],
      };
    if (name === 'Exams' && isStaff)
      return {
        label: 'Schedule exam',
        path: '/exams',
        fields: [
          select('subject_id', 'Subject', subjectOptions),
          text('title', 'Exam title'),
          text('starts_at', 'Date and time', 'datetime-local'),
          text('room', 'Room'),
          {
            name: 'status',
            label: 'Status',
            type: 'select',
            required: true,
            options: ['scheduled', 'postponed', 'cancelled', 'completed'].map((x) => ({
              value: x,
              label: x,
            })),
          },
        ],
      };
    if (name === 'Timetable' && isStaff)
      return {
        label: 'Add timetable class',
        path: '/timetable',
        fields: [
          select('subject_id', 'Subject', subjectOptions),
          {
            name: 'weekday',
            label: 'Weekday (0 Monday – 6 Sunday)',
            type: 'number',
            required: true,
          },
          text('starts_at', 'Starts at (HH:MM)'),
          text('ends_at', 'Ends at (HH:MM)'),
          text('room', 'Room'),
          text('faculty', 'Faculty'),
        ],
      };
    if (name === 'FAQs' && isAdmin)
      return {
        label: 'Add FAQ',
        path: '/faqs',
        fields: [
          select('category_id', 'Category', categoryOptions),
          text('question', 'Question'),
          text('answer', 'Official answer', 'textarea'),
          {
            name: 'published',
            label: 'Published',
            type: 'select',
            required: true,
            options: [
              { value: 'true', label: 'Published' },
              { value: 'false', label: 'Draft' },
            ],
          },
          {
            name: 'featured',
            label: 'Featured',
            type: 'select',
            required: true,
            options: [
              { value: 'true', label: 'Featured' },
              { value: 'false', label: 'Standard' },
            ],
          },
        ],
      };
    return null;
  };
  function openAction(a: Action) {
    setValues(Object.fromEntries(a.fields.map((f) => [f.name, f.defaultValue || ''])));
    setModal(a);
    setError('');
  }
  async function saveAction(e: FormEvent) {
    e.preventDefault();
    if (!modal) return;
    setBusy(true);
    setError('');
    try {
      const body = modal.body
        ? modal.body(values)
        : Object.fromEntries(
            Object.entries(values).map(([k, v]) => [
              k,
              k === 'course_id' && v === ''
                ? null
                : [
                      'course_id',
                      'subject_id',
                      'student_id',
                      'category_id',
                      'year',
                      'weekday',
                      'score',
                      'max_score',
                    ].includes(k) && v !== ''
                  ? Number(v)
                  : ['present', 'published'].includes(k)
                    ? v === 'true'
                    : v,
            ])
          );
      await api(modal.path, token, { method: modal.method || 'POST', body: JSON.stringify(body) });
      if (modal.path === '/profile') setUser(await api('/auth/me', token));
      setModal(null);
      setNotice(`${modal.label} saved`);
      setTimeout(() => setNotice(''), 3000);
      await reload();
      await loadLookups();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function editRow(row: any) {
  const base = actionFor(page);
  if (!base) return;

  let fields = [...base.fields];

  if (page === 'Students') {
    fields = fields.filter(
      (f) => !['student_number', 'password'].includes(f.name)
    );
  }

  if (page === 'Administrators') {
    fields = fields.filter(
      (f) => !['password', 'course_id'].includes(f.name)
    );
  }

  if (page === 'Subjects') {
    fields = fields.filter((f) => f.name !== 'course_id');
  }

  if (page === 'Grades') {
    fields = fields.filter((f) =>
      ['score', 'max_score', 'published'].includes(f.name)
    );
  }

  if (page === 'Assignments') {
    fields = fields.filter((f) => f.name !== 'subject_id');
  }

  const edit = {
    ...base,
    label: `Edit ${page.toLowerCase().replace(/s$/, '')}`,
    path: `${base.path}/${row.id}`,
    method: 'PATCH' as const,
    fields,
  };

  if (page === 'Timetable') {
    edit.path = `/timetable/${row.id}`;
  }

  if (page === 'Exams') {
    edit.path = `/exams/${row.id}`;
  }

  const next: Record<string, string> = {};

  for (const f of fields) {
    let v = row[f.name];

    if (v === undefined || v === null) {
      v = '';
    }

    if (f.type === 'datetime-local' && v) {
      v = new Date(v).toISOString().slice(0, 16);
    }

    if (f.type === 'date' && v) {
      v = String(v).slice(0, 10);
    }

    next[f.name] = String(v);
  }

  setValues(next);
  setModal(edit);
  setError('');
}
  async function sendQuestion(e: FormEvent) {
    e.preventDefault();
    const asked = question;
    setBusy(true);
    setError('');
    try {
      const result = await api('/ai/ask', token, {
        method: 'POST',
        body: JSON.stringify({ question: asked, kind, conversation_id: conversationId }),
      });
      setConversationId(result.conversation_id);
      setAnswer(result.answer);
      setChatSources(result.sources || []);
      setChatMessages((previous) => [
        ...previous,
        { role: 'user', content: asked, created_at: new Date().toISOString() },
        {
          role: 'assistant',
          content: result.answer,
          created_at: new Date().toISOString(),
          sources: result.sources || [],
        },
      ]);
      setQuestion('');
      api('/conversations', token)
        .then((all: any[]) => setChatHistory(all.filter((c) => c.kind === kind)))
        .catch(() => {});
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function openConversation(id: number) {
    try {
      const record = await api(`/conversations/${id}`, token);
      setConversationId(record.id);
      setChatMessages(record.messages);
      setChatSources([]);
      setAnswer('');
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function clearConversation() {
    if (conversationId)
      try {
        await api(`/conversations/${conversationId}`, token, { method: 'DELETE' });
      } catch (e: any) {
        setError(e.message);
        return;
      }
    setConversationId(null);
    setChatMessages([]);
    setChatSources([]);
    setAnswer('');
    api('/conversations', token)
      .then((all: any[]) => setChatHistory(all.filter((c) => c.kind === kind)))
      .catch(() => {});
  }
  function selectPage(name: string) {
    setPage(name);
    setError('');
    if (name === 'Students') setStudentOffset(0);
    if ( name === 'My Campus-Intelligent') {
      setKind(name === 'My Campus-Intelligent' ? 'academic': 'campus');
      setConversationId(null);
      setChatMessages([]);
      setChatSources([]);
      setAnswer('');
    }
  }
  async function submitAssignment(row: any) {
    const content = window.prompt(`Submit your work for “${row.title}”`);
    if (content === null || !content.trim()) return;
    try {
      await api(`/assignments/${row.id}/submissions`, token, {
        method: 'POST',
        body: JSON.stringify({ content }),
      });
      setNotice('Assignment submitted');
      setTimeout(() => setNotice(''), 2500);
      await reload();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function changeStatus(row: any) {
    try {
      await api(`/students/${row.id}/status?active=${row.active === false}`, token, {
        method: 'PATCH',
      });
      await reload();
    } catch (e: any) {
      setError(e.message);
    }
  }

  if (booting)
    return (
      <main className="login">
        <div className="login-card">Loading your secure workspace…</div>
      </main>
    );
  if (!user)
    return (
      <main className="login">
        <form className="login-card" onSubmit={signIn}>
          <div className="brand-mark">
            <GraduationCap />
          </div>
          <p className="eyebrow">UNIVERSITY OPERATING SYSTEM</p>
          <h1>Welcome to Campus Mind</h1>
          <p className="muted">Sign in with your university account.</p>
          <label>
            University ID or email
            <input
              required
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              placeholder="e.g. CSE2026001"
              autoComplete="username"
            />
          </label>
          <label>
            Password
            <input
              required
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error && <div className="error">{error}</div>}
          <button className="primary full" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="tiny">Your role and permissions are verified by the university service.</p>
        </form>
      </main>
    );
  const action = actionFor(page);
  const rows: any[] = Array.isArray(data) ? data : page === 'Analytics' ? data?.courses || [] : [];
  const dashboard = data && typeof data === 'object' && !Array.isArray(data) ? data : {};

  const intelligenceData = intelligence || {};

const intelligenceAttendance =
  Number(intelligenceData.attendance?.average || 0);

const intelligencePerformance =
  Number(intelligenceData.performance?.average || 0);

const intelligenceAtRisk =
  Number(intelligenceData.attendance?.below_75 || 0);

const intelligenceStudents =
  Number(intelligenceData.students || 0);

const intelligenceSubjects =
  Number(intelligenceData.subjects || 0);

const intelligenceAssignments =
  Number(intelligenceData.assignments?.total || 0);

const intelligenceSubmissionRate =
  Number(intelligenceData.assignments?.submission_rate || 0);

const intelligenceAttendanceSubjects =
  intelligenceData.attendance?.by_subject || [];

const intelligencePerformanceSubjects =
  intelligenceData.performance?.by_subject || [];

const intelligenceInsights =
  intelligenceData.insights || [];


const riskData = riskIntelligence || {};

const highRiskStudents =
  riskData.students?.filter(
    (student: any) => student.risk_level === 'High'
  ) || [];

const mediumRiskStudents =
  riskData.students?.filter(
    (student: any) => student.risk_level === 'Medium'
  ) || [];

const highRiskCount =
  Number(riskData.high_risk || 0);

const mediumRiskCount =
  Number(riskData.medium_risk || 0);

const lowRiskCount =
  Number(riskData.low_risk || 0);


  const dashboardCards =
    user.role === 'student'
      ? [
          ['Attendance', `${dashboard.attendance_percent ?? 0}%`],
          ['Academic performance', `${dashboard.average_marks_percent ?? 0}%`],
          ['Pending assignments', dashboard.pending_assignments ?? 0],
          ['Upcoming exams', dashboard.upcoming_exams ?? 0],
        ]
      : user.role === 'course_admin'
        ? [
            ['Enrolled students', dashboard.student_total ?? 0],
            ['Attendance', `${dashboard.attendance_percent ?? 0}%`],
            ['Average marks', `${dashboard.average_marks_percent ?? 0}%`],
            ['Assignments complete', `${dashboard.assignment_completion_percent ?? 0}%`],
          ]
        : [
            ['Students', dashboard.student_total ?? 0],
            ['Courses', dashboard.course_total ?? 0],
            ['Course administrators', dashboard.admin_total ?? 0],
            [
              'Attendance records',
              `${Math.round((dashboard.attendance || 0) * 100)}% average presence`,
            ],
          ];
  const columns = rows.length ? Object.keys(rows[0]) : [];


  const quickActions =
    user.role === 'super_admin'
      ? [
          { label: 'Manage Administrators', page: 'Administrators' },
          { label: 'Manage Students', page: 'Students' },
          { label: 'View Courses', page: 'Courses' },
          { label: 'Open Analytics', page: 'Analytics' },
        ]
      : user.role === 'course_admin'
        ? [
            { label: 'View Students', page: 'Students' },
            { label: 'Mark Attendance', page: 'Attendance' },
            { label: 'Create Assignment', page: 'Assignments' },
            { label: 'Record Grades', page: 'Grades' },
          ]
        : [
            { label: 'Check Attendance', page: 'Attendance' },
            { label: 'View Assignments', page: 'Assignments' },
            { label: 'View Grades', page: 'Grades' },
            { label: 'View Exams', page: 'Exams' },
          ];

  


  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <GraduationCap />
          </div>
          <div>
            <b>Campus Mind</b>
            <small>Intelligent University OS</small>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {rolePages.map((n) => (
            <button
              key={n}
              onClick={() => selectPage(n)}
              className={`nav-item ${page === n ? 'selected' : ''}`}
            >
              <span>{icons[n]}</span>
              {n}
              {n === 'Notifications' && unreadCount > 0 && (
                <b className="nav-count">{unreadCount}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="side-bottom">
          <div className="profile">
            <div className="avatar">{user.full_name.slice(0, 1)}</div>
            <div className="profile-info">
              <b>{user.full_name}</b>
              <small>{user.role.replaceAll('_', ' ')}</small>
            </div>
            <button className="icon-btn" title="Sign out" onClick={signOut}>
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div>
            <span className="crumb">Workspace</span>
            <span className="slash"> / </span>
            <b>{page}</b>
          </div>
          <div className="top-actions">
            <span className="status-dot" /> University services{' '}
            <div className="avatar small-avatar">{user.full_name.slice(0, 1)}</div>
          </div>
        </header>
        <section className="content">
          <div className="welcome">
            <div>
              <p className="eyebrow">
                CAMPUS MIND AI · {user.role.replaceAll('_', ' ').toUpperCase()}
              </p>
              <h1>{page === 'Overview' ? `Good day, ${user.full_name.split(' ')[0]}` : page}</h1>
              <p className="muted">
                {page === 'Overview'
                  ? 'Your academic workspace, connected to university services.'
                  : 'Current information from your university account.'}
              </p>
            </div>
            <div className="welcome-actions">
              {['Students', 'FAQs'].includes(page) && (
                <div className="search">
                  <Search size={17} />
                  <input
                    placeholder={
                      page === 'Students' ? 'Search students' : 'Search frequently asked questions'
                    }
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setStudentOffset(0);
                    }}
                  />
                </div>
              )}
              {action && (
                <button className="primary action-button" onClick={() => openAction(action)}>
                  <Plus size={16} />
                  {action.label}
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="error page-error">
              {error}
              <button onClick={() => setError('')}>
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="notice">
              <Check size={15} />
              {notice}
            </div>
          )}
          {['My Campus-Intelligent'].includes(page) ? (
            <div className="card ai-card">
              <div className="ai-icon">
                <MessageCircle />
              </div>
              <div className="chat-title">
                <div>
                  <h2>{page === 'My Campus-Intelligent'}</h2>
                  <p className="muted">
                    {kind === 'academic'
                      ? 'Your personalized campus intelligence assistant. Ask about your attendance, grades, assignments, and academic improvement priorities.'
                      : 'Your university-aware assistant for campus information, services, and application workflows.'}
                  </p>
                </div>
                <div className="chat-tools">
                  <button
                    className="secondary"
                    onClick={() => {
                      setConversationId(null);
                      setChatMessages([]);
                      setAnswer('');
                    }}
                  >
                    New chat
                  </button>
                  <button className="secondary" onClick={clearConversation}>
                    Clear chat
                  </button>
                </div>
              </div>
              <div className="chat-history">
                <label>
                  Recent conversations
                  <select
                    value={conversationId ?? ''}
                    onChange={(e) => e.target.value && openConversation(Number(e.target.value))}
                  >
                    <option value="">Current conversation</option>
                    {chatHistory.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.kind === 'academic' ? 'Academic' : 'Campus'} -{' '}
                        {new Date(c.created_at).toLocaleString()}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="chat-messages">
                {chatMessages.length === 0 ? (
                  <div className="chat-empty">
                    <div className="ai-icon">
                      <MessageCircle />
                    </div>
                    <b>What can I help you with?</b>
                    <p>Choose a suggestion or ask in your own words.</p>
                  </div>
                ) : (
                  chatMessages.map((m: any, i: number) => (
                    <div
                      className={`chat-message ${m.role === 'user' ? 'from-user' : 'from-ai'}`}
                      key={`${i}-${m.created_at}`}
                    >
                      <span className="message-label">
                        {m.role === 'user' ? 'You' : 'My Campus-Intelligent'}
                      </span>
                      <div className="markdown-content">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {m.content}
                        </ReactMarkdown>
                      </div>
                      <small>
                        {m.created_at
                          ? new Date(m.created_at).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })
                          : ''}
                      </small>
                      {m.sources?.length > 0 && (
                        <div className="sources">
                          Sources:{' '}
                          {m.sources.map((source: any) => (
                            <span key={source.faq_id}>{source.question}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
                {busy && (
                  <div className="chat-message from-ai">
                    <span className="message-label">Assistant</span>
                    <p className="typing">Thinking...</p>
                  </div>
                )}
              </div>
              <div className="suggestions">
                {(kind === 'academic'
                  ? [
                      'Explain my attendance',
                      'What assignments are due?',
                      'Show my grades',
                      'What exams are coming up?',
                    ]
                  : [
                      'How do I submit an assignment?',
                      'Where can I see my attendance?',
                      'What services are available?',
                      'Explain the attendance policy',
                    ]
                ).map((q) => (
                  <button key={q} onClick={() => setQuestion(q)}>
                    {q}
                  </button>
                ))}
              </div>
              <form onSubmit={sendQuestion} className="ask-form">
                <input
                  required
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={
                    kind === 'academic'
                      ? 'Ask about your attendance, grades, or assignments...'
                      : 'Ask about campus services or university workflows...'
                  }
                />
                <button className="primary" disabled={busy}>
                  {busy ? 'Thinking...' : 'Send'}
                </button>
              </form>
            </div>
          
          

          ) : page === 'Overview' ? (
            <>
              <div className="intelligence-header">
                <div>
                  <p className="eyebrow">CAMPUS MIND INTELLIGENCE</p>
                  <h2>University Intelligence Dashboard</h2>
                  <p className="muted">
                    Data-driven academic analytics for your authorized university scope.
                  </p>
                </div>

                <div className="intelligence-live">
                  <span className="status-dot" />
                  Live analytics
                </div>
              </div>

              {busy && !intelligence ? (
                <div className="card data-card">
                  <div className="empty">
                    Loading Campus Mind Intelligence...
                  </div>
                </div>
              ) : (
                <>
                  {/* KPI CARDS */}

                  <div className="stats intelligence-stats">

                    <div className="stat card intelligence-stat">
                      <div className="stat-icon">
                        <Users />
                      </div>

                      <span className="stat-label">
                        {user.role === 'student'
                          ? 'My profile'
                          : 'Students'}
                      </span>

                      <b>{intelligenceStudents}</b>

                      <small>
                        {user.role === 'student'
                          ? 'Personal analytics'
                          : `${intelligenceSubjects} assigned subjects`}
                      </small>
                    </div>


                    <div className="stat card intelligence-stat">
                      <div className="stat-icon">
                        <ClipboardCheck />
                      </div>

                      <span className="stat-label">
                        Attendance
                      </span>

                      <b>{intelligenceAttendance.toFixed(1)}%</b>

                      <small>
                        {intelligenceAtRisk > 0
                          ? `${intelligenceAtRisk} below 75%`
                          : 'No attendance risk detected'}
                      </small>
                    </div>


                    <div className="stat card intelligence-stat">
                      <div className="stat-icon">
                        <ChartNoAxesCombined />
                      </div>

                      <span className="stat-label">
                        Academic performance
                      </span>

                      <b>{intelligencePerformance.toFixed(1)}%</b>

                      <small>
                        Published grade records
                      </small>
                    </div>


                    <div className="stat card intelligence-stat">
                      <div className="stat-icon">
                        <Activity />
                      </div>

                      <span className="stat-label">
                        Students at risk
                      </span>

                      <b>{intelligenceAtRisk}</b>

                      <small>
                        Attendance below 75%
                      </small>
                    </div>

                  </div>


                  {/* SUBJECT PERFORMANCE + ATTENDANCE */}

                  <div className="overview-grid intelligence-grid">

                    <div className="card data-card">
                      <div className="card-head">
                        <div>
                          <h2>Performance by Subject</h2>
                          <p className="muted">
                            Average published academic performance.
                          </p>
                        </div>
                      </div>

                      {intelligencePerformanceSubjects.length ? (
                        <div className="intelligence-bars">
                          {intelligencePerformanceSubjects.map((subject: any) => (
                            <IntelligenceBar
                              key={subject.subject}
                              label={`${subject.subject} — ${subject.name}`}
                              value={subject.average}
                            />
                          ))}
                        </div>
                      ) : (
                        <div className="empty">
                          No published performance data available.
                        </div>
                      )}
                    </div>


                    <div className="card data-card">
                      <div className="card-head">
                        <div>
                          <h2>Attendance by Subject</h2>
                          <p className="muted">
                            Attendance calculated from recorded classes.
                          </p>
                        </div>
                      </div>

                      {intelligenceAttendanceSubjects.length ? (
                        <div className="intelligence-bars">
                          {intelligenceAttendanceSubjects.map((subject: any) => (
                            <IntelligenceBar
                              key={subject.subject}
                              label={`${subject.subject} — ${subject.name}`}
                              value={subject.percentage}
                            />
                          ))}
                        </div>
                      ) : (
                        <div className="empty">
                          No attendance data available.
                        </div>
                      )}
                    </div>

                  </div>


                  {/* ASSIGNMENT ANALYTICS */}

                  <div className="overview-grid">

                    <div className="card data-card">
                      <div className="card-head">
                        <div>
                          <h2>Assignment Analytics</h2>
                          <p className="muted">
                            Assignment activity within your authorized scope.
                          </p>
                        </div>
                      </div>

                      <div className="assignment-intelligence">

                        <div>
                          <span>Total assignments</span>
                          <b>{intelligenceAssignments}</b>
                        </div>

                        <div>
                          <span>Submission rate</span>
                          <b>{intelligenceSubmissionRate.toFixed(1)}%</b>
                        </div>

                      </div>

                      <div className="intelligence-bar-row">
                        <div className="intelligence-bar-label">
                          <span>Submission completion</span>
                          <b>{intelligenceSubmissionRate.toFixed(1)}%</b>
                        </div>

                        <div className="intelligence-bar-track">
                          <div
                            className="intelligence-bar-fill"
                            style={{
                              width: `${Math.min(
                                100,
                                Math.max(0, intelligenceSubmissionRate)
                              )}%`,
                            }}
                          />
                        </div>
                      </div>

                    </div>


                    {/* RISK */}

                    <div className="card data-card">
                      <div className="card-head">
                        <div>
                          <h2>Risk Overview</h2>
                          <p className="muted">
                            Students requiring attendance attention.
                          </p>
                        </div>
                      </div>

                      {intelligenceAtRisk > 0 ? (
                        <div className="risk-highlight">
                          <div className="risk-number">
                            {intelligenceAtRisk}
                          </div>

                          <div>
                            <b>Students below 75% attendance</b>
                            <p>
                              These students may require academic follow-up
                              or attendance review.
                            </p>
                          </div>
                        </div>
                      ) : (
                        <div className="empty">
                          No students are currently below the 75% attendance
                          threshold.
                        </div>
                      )}

                    </div>

                  </div>
                  


                  
                  <section className="card intelligence-risk-section">
                    <div className="section-heading">
                      <div>
                        <h3>Student Risk Analysis</h3>
                        <p>
                          Students identified using attendance, academic performance,
                          and assignment activity.
                        </p>
                      </div>
                    </div>

                    <div className="risk-summary-grid">
                      <div className="risk-summary-card risk-high">
                        <span>High Risk</span>
                        <strong>{highRiskCount}</strong>
                        <small>Multiple academic risk indicators</small>
                      </div>

                      <div className="risk-summary-card risk-medium">
                        <span>Medium Risk</span>
                        <strong>{mediumRiskCount}</strong>
                        <small>Requires monitoring</small>
                      </div>

                      <div className="risk-summary-card risk-low">
                        <span>Low Risk</span>
                        <strong>{lowRiskCount}</strong>
                        <small>No major risk indicators</small>
                      </div>
                    </div>

                    {highRiskStudents.length > 0 ? (
                      <div className="risk-student-list">

                        <div className="risk-list-header">
                          <div>
                            <h4>High-Risk Students</h4>
                            <small>
                              Students requiring immediate academic attention
                            </small>
                          </div>

                          <span>
                            {highRiskStudents.length} student
                            {highRiskStudents.length !== 1 ? 's' : ''}
                          </span>
                        </div>

                        {highRiskStudents.slice(0, 5).map((student: any) => (
                          <div
                            key={student.student_id}
                            className="risk-student-row"
                          >
                            <div className="risk-student-main">
                              <strong>{student.name}</strong>

                              <small>{student.student_number}</small>

                              <div className="risk-factor-list">
                                {student.risk_factors?.length ? (
                                  student.risk_factors.map(
                                    (factor: string) => (
                                      <span key={factor}>
                                        {factor}
                                      </span>
                                    )
                                  )
                                ) : (
                                  <span>No specific risk factor recorded</span>
                                )}
                              </div>
                            </div>

                            <div className="risk-metrics">
                              <div>
                                <small>Attendance</small>
                                <strong>
                                  {Number(student.attendance || 0).toFixed(1)}%
                                </strong>
                              </div>

                              <div>
                                <small>Performance</small>
                                <strong>
                                  {Number(student.performance || 0).toFixed(1)}%
                                </strong>
                              </div>

                              <div>
                                <small>Assignments</small>
                                <strong>
                                  {Number(
                                    student.assignment_completion || 0
                                  ).toFixed(1)}%
                                </strong>
                              </div>

                              <div>
                                <small>Risk score</small>
                                <strong>
                                  {student.risk_score}
                                </strong>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : mediumRiskStudents.length > 0 ? (
                      <div className="risk-student-list">

                        <div className="risk-list-header">
                          <div>
                            <h4>Students Requiring Monitoring</h4>
                            <small>
                              No high-risk students were identified, so
                              medium-risk students are shown for monitoring.
                            </small>
                          </div>

                          <span>
                            {mediumRiskStudents.length} student
                            {mediumRiskStudents.length !== 1 ? 's' : ''}
                          </span>
                        </div>

                        {mediumRiskStudents.slice(0, 5).map((student: any) => (
                          <div
                            key={student.student_id}
                            className="risk-student-row"
                          >
                            <div className="risk-student-main">
                              <strong>{student.name}</strong>

                              <small>{student.student_number}</small>

                              <div className="risk-factor-list">
                                {student.risk_factors?.length ? (
                                  student.risk_factors.map(
                                    (factor: string) => (
                                      <span key={factor}>
                                        {factor}
                                      </span>
                                    )
                                  )
                                ) : (
                                  <span>Requires academic monitoring</span>
                                )}
                              </div>
                            </div>

                            <div className="risk-metrics">
                              <div>
                                <small>Attendance</small>
                                <strong>
                                  {Number(student.attendance || 0).toFixed(1)}%
                                </strong>
                              </div>

                              <div>
                                <small>Performance</small>
                                <strong>
                                  {Number(student.performance || 0).toFixed(1)}%
                                </strong>
                              </div>

                              <div>
                                <small>Assignments</small>
                                <strong>
                                  {Number(
                                    student.assignment_completion || 0
                                  ).toFixed(1)}%
                                </strong>
                              </div>

                              <div>
                                <small>Risk score</small>
                                <strong>
                                  {student.risk_score}
                                </strong>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="risk-empty-state">
                        No students currently require academic-risk monitoring
                        in the authorized data.
                      </div>
                    )}
                  </section>




                  {/* AI INSIGHTS */}

                  <div className="card data-card intelligence-insights">

                    <div className="card-head">
                      <div>
                        <h2>AI Insights</h2>
                        <p className="muted">
                          Observations generated from verified university data.
                        </p>
                      </div>

                      <MessageCircle size={20} />
                    </div>

                    {intelligenceInsights.length ? (
                      <div className="insight-list">
                        {intelligenceInsights.map(
                          (insight: string, index: number) => (
                            <div
                              className="insight-item"
                              key={`${index}-${insight}`}
                            >
                              <div className="insight-number">
                                {index + 1}
                              </div>

                              <div>
                                <b>Campus Mind Intelligence</b>
                                <p>{insight}</p>
                              </div>
                            </div>
                          )
                        )}
                      </div>
                    ) : (
                      <div className="empty">
                        No new intelligence insights are available.
                      </div>
                    )}

                  </div>


                  {/* QUICK ACTIONS */}

                  <div className="card quick-actions-card">

                    <div className="card-head">
                      <div>
                        <h2>Quick actions</h2>
                        <p className="muted">
                          Frequently used university workflows.
                        </p>
                      </div>
                    </div>

                    <div className="quick-actions">

                      {quickActions.map((item) => (
                        <button
                          key={item.page}
                          className="quick-action"
                          onClick={() => selectPage(item.page)}
                        >
                          <span>{item.label}</span>
                          <ChevronRight size={15} />
                        </button>
                      ))}

                    </div>

                  </div>


                  {/* EXISTING ANNOUNCEMENTS / WORKSPACE */}

                  <div className="overview-grid">

                    <div className="card data-card">

                      <div className="card-head">
                        <div>
                          <h2>Announcements</h2>
                          <p className="muted">
                            Latest updates for your access scope.
                          </p>
                        </div>

                        <button
                          className="text-button"
                          onClick={() => setPage('Announcements')}
                        >
                          View all <ChevronRight size={14} />
                        </button>
                      </div>

                      {dashboard.announcements?.length ? (
                        dashboard.announcements.map((a: any) => (
                          <article
                            className="announcement"
                            key={a.id}
                          >
                            <b>{a.title}</b>
                            <p>{a.body}</p>
                          </article>
                        ))
                      ) : (
                        <div className="empty">
                          No announcements have been published.
                        </div>
                      )}

                    </div>


                    <div className="card data-card">

                      <div className="card-head">

                        <div>
                          <h2>
                            {user.role === 'student'
                              ? 'Upcoming campus events'
                              : 'Academic workspace'}
                          </h2>

                          <p className="muted">
                            Your next steps and scheduled activities.
                          </p>
                        </div>

                      </div>

                      {dashboard.events?.length ? (
                        dashboard.events.map((e: any) => (
                          <div
                            className="event-row"
                            key={e.id}
                          >
                            <CalendarDays size={17} />

                            <div>
                              <b>{e.title}</b>
                              <small>{pretty(e.starts_at)}</small>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="empty">
                          {user.role === 'student'
                            ? 'No upcoming events.'
                            : 'Use the workspace menu to manage university workflows.'}
                        </div>
                      )}

                    </div>

                  </div>
                </>
              )}
            </>

          



          ) : page === 'Profile' ? (
            <div className="card data-card profile-card">
              <div className="card-head">
                <div>
                  <h2>Your profile</h2>
                  <p className="muted">Update the contact details associated with this account.</p>
                </div>
              </div>
              <dl>
                <dt>University ID</dt>
                <dd>{dashboard.login}</dd>
                <dt>Name</dt>
                <dd>{dashboard.full_name}</dd>
                <dt>Email</dt>
                <dd>{dashboard.email}</dd>
                <dt>Role</dt>
                <dd>{String(dashboard.role || '').replaceAll('_', ' ')}</dd>
                {dashboard.course_id && (
                  <>
                    <dt>Assigned course</dt>
                    <dd>
                      {courseRows.find((c) => c.id === dashboard.course_id)?.name ||
                        dashboard.course_id}
                    </dd>
                  </>
                )}
              </dl>
            </div>
          ) : page === 'FAQs' ? (
            <div className="faq-page card data-card">
              <div className="faq-categories">
                <button className={!faqCategory ? 'active' : ''} onClick={() => setFaqCategory('')}>
                  All topics
                </button>
                {categoryRows.map((c) => (
                  <button
                    className={faqCategory === String(c.id) ? 'active' : ''}
                    onClick={() => setFaqCategory(String(c.id))}
                    key={c.id}
                  >
                    {c.name}
                  </button>
                ))}
              </div>
              {busy ? (
                <div className="empty">Loading FAQs...</div>
              ) : rows.length === 0 ? (
                <div className="empty">
                  No FAQs match your search. Try other words or another category.
                </div>
              ) : (
                <div className="faq-list">
                  {rows.map((faq: any) => (
                    <details className="faq-item" key={faq.id}>
                      <summary>
                        <span>
                          {faq.question}
                          {faq.featured && <b className="featured-tag">Popular</b>}
                          {isAdmin && !faq.published && <b className="draft-tag">Draft</b>}
                        </span>
                        <small>{faq.category}</small>
                      </summary>
                      <div className="faq-answer">
                        <p>{faq.answer}</p>
                        <div className="faq-actions">
                          <span>Was this helpful?</span>
                          <button
                            onClick={async (e) => {
                              e.preventDefault();
                              try {
                                await api(`/faq-feedback/${faq.id}`, token, {
                                  method: 'POST',
                                  body: JSON.stringify({ helpful: true }),
                                });
                                setNotice('Feedback recorded');
                                setTimeout(() => setNotice(''), 2000);
                              } catch (err: any) {
                                setError(err.message);
                              }
                            }}
                          >
                            Yes
                          </button>
                          <button
                            onClick={async (e) => {
                              e.preventDefault();
                              try {
                                await api(`/faq-feedback/${faq.id}`, token, {
                                  method: 'POST',
                                  body: JSON.stringify({ helpful: false }),
                                });
                                setNotice('Feedback recorded');
                                setTimeout(() => setNotice(''), 2000);
                              } catch (err: any) {
                                setError(err.message);
                              }
                            }}
                          >
                            No
                          </button>
                          {isAdmin && (
                            <>
                              <button
                                onClick={(e) => {
                                  e.preventDefault();
                                  editRow(faq);
                                }}
                              >
                                Edit
                              </button>
                              <button
                                className="danger-text"
                                onClick={async (e) => {
                                  e.preventDefault();
                                  try {
                                    await api(`/faqs/${faq.id}`, token, { method: 'DELETE' });
                                    reload();
                                  } catch (err: any) {
                                    setError(err.message);
                                  }
                                }}
                              >
                                Archive
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </div>
          ) : page === 'Analytics' ? (
            <>
              <div className="stats">
                <div className="stat card">
                  <span className="stat-label">Total students</span>
                  <b>{dashboard.student_total ?? 0}</b>
                </div>
                <div className="stat card">
                  <span className="stat-label">Attendance rate</span>
                  <b>{dashboard.attendance_percent ?? 0}%</b>
                </div>
                <div className="stat card">
                  <span className="stat-label">Active accounts</span>
                  <b>{dashboard.active_users ?? 0}</b>
                </div>
                <div className="stat card">
                  <span className="stat-label">Attendance records</span>
                  <b>{dashboard.attendance_records ?? 0}</b>
                </div>
                <div className="stat card">
                  <span className="stat-label">Average marks</span>
                  <b>{dashboard.average_marks_percent ?? 0}%</b>
                </div>
                <div className="stat card">
                  <span className="stat-label">Assignment completion</span>
                  <b>{dashboard.assignment_completion_percent ?? 0}%</b>
                </div>
              </div>
              <div className="card data-card">
                <div className="card-head">
                  <div>
                    <h2>Course distribution</h2>
                    <p className="muted">Current student enrollment by engineering course.</p>
                  </div>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Course</th>
                        <th>Students</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r: any) => (
                        <tr key={r.course_id}>
                          <td>{r.code}</td>
                          <td>{r.students}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="overview-grid analytics-lists">
                <div className="card data-card">
                  <h2>Attendance risk</h2>
                  <p className="muted">
                    Students below the configured {dashboard.attendance_alert_threshold}% threshold.
                  </p>
                  {dashboard.attendance_risk_students?.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Student</th>
                            <th>Course</th>
                            <th>Attendance</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dashboard.attendance_risk_students.map((r: any) => (
                            <tr key={r.student_id}>
                              <td>
                                {r.student_number} · {r.full_name}
                              </td>
                              <td>{r.course}</td>
                              <td>{r.attendance_percent}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="empty">
                      No students are currently below the configured threshold.
                    </div>
                  )}
                </div>
                <div className="card data-card">
                  <h2>Academic performance</h2>
                  <p className="muted">Highest published grade averages.</p>
                  {dashboard.top_performers?.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Student</th>
                            <th>Course</th>
                            <th>Average</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dashboard.top_performers.map((r: any) => (
                            <tr key={r.student_id}>
                              <td>
                                {r.student_number} · {r.full_name}
                              </td>
                              <td>{r.course}</td>
                              <td>{r.average_marks_percent}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="empty">No published grades are available yet.</div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="card data-card">
              <div className="card-head">
                <div>
                  <h2>{page}</h2>
                  <p className="muted">
                    {rows.length} record{rows.length === 1 ? '' : 's'} · served by Campus Mind API
                  </p>
                </div>
                <span className="live-tag">
                  <i /> Live
                </span>
              </div>
              {busy ? (
                <div className="empty">Loading university data…</div>
              ) : rows.length === 0 ? (
                <div className="empty">
                  No records yet. Use the action above to add the first one, or seed the demo
                  database.
                </div>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {columns.map((k) => (
                          <th key={k}>{k.replaceAll('_', ' ')}</th>
                        ))}
                        {[
                          'Students',
                          'Administrators',
                          'Courses',
                          'Subjects',
                          'Assignments',
                          'Grades',
                          'Announcements',
                          'Events',
                          'FAQs',
                          'Exams',
                          'Timetable',
                        ].includes(page) &&
                          action && <th>Manage</th>}
                        {page === 'Assignments' && user.role === 'student' && <th>Action</th>}
                        {page === 'Students' && isAdmin && <th>Status</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => (
                        <tr key={row.id || i}>
                          {columns.map((k) => (
                            <td key={k}>{pretty(row[k])}</td>
                          ))}
                          {[
                            'Students',
                            'Administrators',
                            'Courses',
                            'Subjects',
                            'Assignments',
                            'Grades',
                            'Announcements',
                            'Events',
                            'FAQs',
                            'Exams',
                            'Timetable',
                          ].includes(page) &&
                            action && (
                              <td>
                                <button className="table-action" onClick={() => editRow(row)}>
                                  Edit
                                </button>
                              </td>
                            )}
                          {page === 'Assignments' && user.role === 'student' && (
                            <td>
                              <button
                                className="table-action"
                                disabled={row.submitted}
                                onClick={() => submitAssignment(row)}
                              >
                                {row.submitted ? 'Submitted' : 'Submit work'}
                              </button>
                            </td>
                          )}
                          {page === 'Students' && isAdmin && (
                            <td>
                              <button className="table-action" onClick={() => changeStatus(row)}>
                                {row.active === false ? 'Reactivate' : 'Deactivate'}
                              </button>
                            </td>
                          )}
                          {page === 'Notifications' && (
                            <td>
                              <button
                                className="table-action"
                                onClick={async () => {
                                  try {
                                    await api(`/notifications/${row.id}`, token, {
                                      method: 'PATCH',
                                      body: JSON.stringify({ read: true }),
                                    });
                                    reload();
                                  } catch (e: any) {
                                    setError(e.message);
                                  }
                                }}
                              >
                                {row.read ? 'Read' : 'Mark read'}
                              </button>
                            </td>
                          )}
                          {page === 'FAQs' && isAdmin && (
                            <td>
                              <button
                                className="table-action danger-text"
                                onClick={async () => {
                                  try {
                                    await api(`/faqs/${row.id}`, token, { method: 'DELETE' });
                                    reload();
                                  } catch (e: any) {
                                    setError(e.message);
                                  }
                                }}
                              >
                                Archive
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {page === 'Students' && isAdmin && (
                <div className="pagination">
                  <span>
                    Showing {rows.length ? studentOffset + 1 : 0}–{studentOffset + rows.length}
                  </span>
                  <button
                    className="secondary"
                    disabled={studentOffset === 0 || busy}
                    onClick={() => setStudentOffset(Math.max(0, studentOffset - 100))}
                  >
                    Previous
                  </button>
                  <button
                    className="secondary"
                    disabled={rows.length < 100 || busy}
                    onClick={() => setStudentOffset(studentOffset + 100)}
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          )}
          <footer>
            Campus Mind AI <span>·</span> Secure academic workspace{' '}
            <button
              className="text-button"
              onClick={() => window.open(`${API.replace('/api', '')}/docs`, '_blank')}
            >
              API documentation <ChevronRight size={13} />
            </button>
          </footer>
        </section>
      </main>
      {modal && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setModal(null);
          }}
        >
          <form className="modal" onSubmit={saveAction}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">UNIVERSITY WORKFLOW</p>
                <h2>{modal.label}</h2>
              </div>
              <button type="button" className="icon-btn" onClick={() => setModal(null)}>
                <X />
              </button>
            </div>
            <div className="form-grid">
              {modal.fields.map((f) => (
                <label key={f.name} className={f.type === 'textarea' ? 'wide' : ''}>
                  {f.label}
                  {f.type === 'select' ? (
                    <select
                      required={f.required}
                      value={values[f.name] || ''}
                      onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                    >
                      <option value="">Select…</option>
                      {f.options?.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  ) : f.type === 'textarea' ? (
                    <textarea
                      required={f.required}
                      rows={4}
                      value={values[f.name] || ''}
                      onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                    />
                  ) : (
                    <input
                      required={f.required}
                      type={f.type || 'text'}
                      min={f.type === 'number' ? 1 : undefined}
                      value={values[f.name] || ''}
                      onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                    />
                  )}
                </label>
              ))}
            </div>
            {error && <div className="error">{error}</div>}
            <div className="modal-actions">
              <button type="button" className="secondary" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button className="primary" disabled={busy}>
                {busy ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
