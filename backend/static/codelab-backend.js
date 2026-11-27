// Same-origin transport for the bundled Vue client. Demo accounts keep their original methods.
export function connectBackend(api, state, ApiError) {
  const original = { ...api };
  const navigation = performance.getEntriesByType('navigation')[0];
  const clientId = (navigation?.type === 'reload' && sessionStorage.getItem('codelab-tab-id')) || crypto.randomUUID();
  sessionStorage.setItem('codelab-tab-id', clientId);
  let profile = null;
  let activeExam = null;
  let session = null;
  let renew;
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
      headers:{'Content-Type':'application/json', ...(profile && method !== 'GET' ? {'X-CodeLab-User':profile.id} : {}), ...(session ? {'X-Exam-Session':session} : {}), ...headers},
      body:data === undefined ? undefined : JSON.stringify(data),
    });
    const reply = await res.json();
    if (!res.ok) throw new ApiError(res.status, reply.message, reply.request_id);
    return reply.data;
  }
  function endSession() {
    clearInterval(renew);
    if (activeExam && session) request('/exams/'+activeExam+'/sessions','DELETE').catch(()=>{});
    activeExam = session = null;
  }
  function leave() {
    endSession();
    if (profile) {
      const prefixes=['codelab-draft-','codelab-chat-','codelab-unsynced-','codelab-submit-'].map(p=>p+profile.id+':');
      for (const key of Object.keys(sessionStorage)) {
        if (prefixes.some(prefix=>key.startsWith(prefix))) sessionStorage.removeItem(key);
      }
    }
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
    Object.assign(state,{problems,exams:await request('/exams'),submissions:await request('/submissions'),classes:await request('/classes'),banks:banks.filter(b=>b.id!=='builtin').map(b=>b.name),users:[],keys:[],audits:[],aiUsage:{}});
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
    const workspace = to.path.startsWith('/workspace/');
    const eid = workspace ? to.query.exam : (to.name !== 'exam-builder' && to.params.id && to.path.startsWith('/exams/') ? to.params.id : null);
    if (activeExam && (!workspace || activeExam!==eid)) endSession();
    if (eid) upsert(state.exams,await request('/exams/'+encodeURIComponent(eid)));
    if (workspace) {
      const pid = to.params.id;
      if(eid && !state.exams.find(e=>e.id===eid)?.receipt && !session) {
        activeExam = eid;
        const acquire = async () => {
          const lease = await request('/exams/'+eid+'/sessions','POST',{client_id:clientId});
          if(activeExam===eid) session = lease.session_id;
        };
        await acquire();
        clearInterval(renew); renew=setInterval(()=>acquire().catch(()=>{}),30000);
      }
      const scope=eid || 'practice-'+pid;
      const key=profile.id+':'+scope+':'+pid;
      try {
        const draft=await request('/drafts/'+encodeURIComponent(key));
        sessionStorage.setItem('codelab-draft-'+key,JSON.stringify(draft));
        sessionStorage.setItem('codelab-chat-'+key,JSON.stringify(draft.aiHistory||[]));
      } catch(e) {
        if(e.status!==404)throw e;
        sessionStorage.removeItem('codelab-draft-'+key);
        sessionStorage.removeItem('codelab-chat-'+key);
      }
    }
    return profile;
  }
  function reference(pid,eid) {
    const problem=state.exams.find(e=>e.id===eid)?.snapshots?.find(p=>p.id===pid)||state.problems.find(p=>p.id===pid);
    if(!problem) throw new Error('题目不存在或无权访问');
    return pid+'@'+problem.version;
  }
  async function job(path, data, update) {
    const accepted=await request(path,'POST',{...data, async:true});
    update?.({id:accepted.id,status:'queued',events:[]});
    for (;;) {
      const task=await request('/jobs/'+accepted.id);
      update?.(task);
      if (!['queued','running'].includes(task.status)) {
        if(['done','code_error'].includes(task.status))return task.result;
        throw new Error(task.error||'任务未完成');
      }
      await new Promise(resolve=>setTimeout(resolve,750));
    }
  }
  const remote={
    login:(username,password,remember)=>authenticate('login',{username,password,remember}),
    register:(username,password,nickname,remember)=>authenticate('register',{username,password,nickname,remember}),
    async saveDraft(key,draft) {
      try {
        const result=await request('/drafts/'+encodeURIComponent(key),'PUT',draft);
        sessionStorage.setItem('codelab-draft-'+key,JSON.stringify(result));
        return result;
      } catch(e) {
        if(e.status===409) {
          const confirmed=await request('/drafts/'+encodeURIComponent(key)).catch(()=>null);
          if(confirmed)sessionStorage.setItem('codelab-draft-'+key,JSON.stringify(confirmed));
        }
        throw e;
      }
    },
    async submit(pid,files,explanation,idempotencyKey,eid,history=[]) {
      return upsert(state.submissions,await request('/submissions','POST',{problem_version_id:reference(pid,eid),
        files,explanation,exam_id:eid,ai_history:history},{'Idempotency-Key':idempotencyKey}));
    },
    submission:id=>request('/submissions/'+id),
    async createExam(exam) {
      const created=await request(exam.personal?'/mock-exams':'/exams','POST',exam);
      exam.id=created.id;
      return upsert(state.exams,created);
    },
    async handIn(eid) {
      const sheet=await request('/exams/'+eid+'/answer-sheet','POST',{});
      upsert(state.exams,await request('/exams/'+eid)); return sheet;
    },
    run:(pid,files)=>job('/runs',{problem_version_id:reference(pid,activeExam),exam_id:activeExam,files}),
  };
  for(const [name,handler] of Object.entries(remote)) {
    api[name]=(...args)=>profile||name==='login'||name==='register'?handler(...args):original[name](...args);
  }
  return {
    route, get live(){return !!profile;},
    get examReadOnly(){return !!activeExam && !session;},
    versions:key=>request('/drafts/'+encodeURIComponent(key)+'/versions'),
    async restoreDraft(key,version,expected_version) {
      const draft=await request('/drafts/'+encodeURIComponent(key)+'/restore','POST',{version,expected_version});
      sessionStorage.setItem('codelab-draft-'+key,JSON.stringify(draft));
      return draft;
    },
    runCommand:(pid,files,command,update)=>job('/runs',{problem_version_id:reference(pid,activeExam),
      exam_id:activeExam,files,command:command||undefined},update),
    cancelJob:id=>request('/jobs/'+encodeURIComponent(id)+'/cancel','POST',{}),
    async logout(){if(profile){await request('/auth/logout','POST',{});leave();}},
    async changePassword(old_password,new_password){await request('/users/me/password','POST',{old_password,new_password});leave();},
    async updateProfile(data){profile=await request('/users/me','PATCH',data);return profile;}
  };
}
