// Same-origin transport for the bundled Vue client. Demo accounts keep their original methods.
export function connectBackend(api, state, ApiError) {
  const original = { ...api };
  let profile = null;
  let localState;
  const copy = value => JSON.parse(JSON.stringify(value));
  const keys = ['problems', 'exams', 'classes', 'submissions', 'banks', 'users', 'keys', 'audits', 'aiUsage'];
  function clearLocalSession() {
    localStorage.removeItem('codelab-session-v1');
    sessionStorage.removeItem('codelab-session-v1');
  }
  async function request(path, method='GET', data, headers={}) {
    const res = await fetch('/api/v1' + path, {
      method, credentials:'same-origin', cache:'no-store',
      headers:{'Content-Type':'application/json', ...(profile && method !== 'GET' ? {'X-CodeLab-User':profile.id} : {}), ...headers},
      body:data === undefined ? undefined : JSON.stringify(data),
    });
    const reply = await res.json();
    if (!res.ok) throw new ApiError(res.status, reply.message, reply.request_id);
    return reply.data;
  }
  function leave() {
    if (localState) Object.assign(state,localState);
    localState = undefined;
    profile = null;
  }
  async function authenticate(operation, data) {
    const user = await request('/auth/'+operation, 'POST', data);
    clearLocalSession();
    await load(user);
    return user;
  }
  async function projectList(manage=false) {
    const rows = [];
    for (let page=1;;page++) {
      const result = await request('/problems?page_size=100&page='+page+(manage?'&manage=1':''));
      rows.push(...result.items);
      if (!result.items.length || rows.length >= result.total) return rows;
    }
  }
  async function load(user) {
    if (!localState) localState = Object.fromEntries(keys.map(k=>[k,copy(state[k])]));
    profile = user;
    const [problems,banks] = await Promise.all([projectList(),request('/banks')]);
    Object.assign(state,{problems,exams:await request('/exams'),submissions:[],classes:await request('/classes'),banks:banks.filter(b=>b.id!=='builtin').map(b=>b.name),users:[],keys:[],audits:[],aiUsage:{}});
  }
  function upsert(rows,value) {
    const previous=rows.find(r=>r.id===value.id);
    if(previous) Object.assign(previous,value);
    else rows.unshift(value);
    return value;
  }
  async function route(to, localUser) {
    let user;
    try { user = await request('/users/me'); }
    catch (error) {
      if (error.status !== 401) throw error;
      if (profile) leave();
      clearLocalSession();
      return null;
    }
    if (!profile || profile.id !== user.id || profile.role !== user.role) {
      if (profile) leave();
      clearLocalSession();
      await load(user);
    } else {
      profile = user;
    }
    const manageProjects = to.path === '/banks' || to.path.startsWith('/problem-edit');
    if (manageProjects || ['/problems','/exams/new','/mock'].includes(to.path)) {
      const [problems,banks] = await Promise.all([projectList(manageProjects),request('/banks')]);
      state.problems = problems;
      state.banks = banks.filter(b => b.id !== 'builtin').map(b => b.name);
    }
    if (['/classes','/exams/new'].includes(to.path)) state.classes = await request('/classes');
    if (['/exams'].includes(to.path)) state.exams = await request('/exams');
    if (to.params.id && to.path.startsWith('/exams/')) upsert(state.exams,await request('/exams/'+encodeURIComponent(to.params.id)));
    return profile;
  }
  const remote={
    login:(username,password,remember)=>authenticate('login',{username,password,remember}),
    register:(username,password,nickname,remember)=>authenticate('register',{username,password,nickname,remember}),
    async createExam(exam) {
      const created=await request(exam.personal?'/mock-exams':'/exams','POST',exam);
      exam.id=created.id;
      return upsert(state.exams,created);
    },
  };
  for(const [name,handler] of Object.entries(remote)) {
    api[name]=(...args)=>profile||name==='login'||name==='register'?handler(...args):original[name](...args);
  }
  return {
    route, get live(){return !!profile;},
    async logout(){if(profile){await request('/auth/logout','POST',{});leave();}},
    async changePassword(old_password,new_password){await request('/users/me/password','POST',{old_password,new_password});leave();},
    async updateProfile(data){profile=await request('/users/me','PATCH',data);return profile;}
  };
}
