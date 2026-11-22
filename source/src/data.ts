import type { Problem, Exam, Submission, ProjectFiles } from "./types";
import { defaultWeights } from "./domain";
export const taskTypes = [
  "需求实现",
  "代码理解",
  "缺陷修复",
  "工程重构",
] as const;
export const stacks = [
  "Vue 3 / TypeScript",
  "Node.js / TypeScript",
  "Python 3.12 / pytest",
];

type Seed = {
  title: string;
  type: Problem["type"];
  stack: number;
  difficulty: Problem["difficulty"];
  duration: number;
  repo: string;
  entry: string;
  description: string;
  requirements: string[];
  cases: [string, string][];
  code: string;
  test: string;
  extra?: ProjectFiles;
};
const entries: Seed[] = [
  {
    title: "工单协作台：新增指派与状态流转",
    type: "需求实现",
    stack: 0,
    difficulty: "中等",
    duration: 90,
    repo: "support-desk",
    entry: "src/tickets.ts",
    description:
      "客服团队已有工单列表和详情页，但工单只能查看。产品要求让负责人可以认领、处理和关闭工单。阅读现有状态管理与组件，完成操作入口、状态流转和错误反馈，并保持列表与详情一致。",
    requirements: [
      "待处理工单可指派给团队成员；已停用成员不可接单。",
      "状态按待处理 → 处理中 → 已解决流转；未指派不可开始处理，关闭时必须填写解决说明。",
      "列表与详情共享同一份状态；失败操作不应改变原有工单。",
    ],
    cases: [
      [
        "将 T-101 指派给林同学后开始处理",
        "列表与详情均显示处理中，并记录负责人",
      ],
      [
        "未指派时开始处理，或选择停用成员",
        "显示原因，工单状态和负责人保持原值",
      ],
      ["关闭工单但解决说明为空", "拒绝关闭；补充说明后可进入已解决"],
    ],
    code: `export type Ticket = { id: string; title: string; status: 'open' | 'active' | 'resolved'; assignee: string | null; resolution: string };
export type Member = { id: string; name: string; enabled: boolean };
export const members: Member[] = [{ id: 'lin', name: '林同学', enabled: true }, { id: 'chen', name: '陈同学', enabled: false }];
export const seedTickets: Ticket[] = [{ id: 'T-101', title: '导出报表失败', status: 'open', assignee: null, resolution: '' }];
export function updateTicket(ticket: Ticket, changes: Partial<Ticket>): Ticket {
  return { ...ticket, ...changes };
}
`,
    test: `import { describe, it, expect } from 'vitest';
import { seedTickets, updateTicket } from '../src/tickets';
describe('工单流转', () => {
  it('未指派不可开始处理', () => {
    expect(() => updateTicket(seedTickets[0], { status: 'active' })).toThrow();
  });
  it('不直接修改原工单', () => {
    const original = { ...seedTickets[0] };
    updateTicket(original, { assignee: 'lin' });
    expect(original.assignee).toBeNull();
  });
});
`,
    extra: {
      "src/App.vue": `<script setup lang="ts">
import { ref } from 'vue';
import { seedTickets } from './tickets';
const tickets = ref(seedTickets.map(t => ({ ...t })));
const selected = ref('T-101');
</script>
<template>
  <main><h1>客服工单</h1>
    <button v-for="ticket in tickets" :key="ticket.id" @click="selected = ticket.id">{{ ticket.title }} · {{ ticket.status }}</button>
    <section v-for="ticket in tickets.filter(t => t.id === selected)" :key="ticket.id"><h2>{{ ticket.title }}</h2><p>负责人：{{ ticket.assignee || '未指派' }}</p></section>
  </main>
</template>
`,
      "docs/product.md":
        "# 工单状态约定\nopen：待处理；active：处理中；resolved：已解决。\n已解决工单本轮无需支持重开。成员目录来自 src/tickets.ts。\n交互应支持键盘操作，错误反馈应与触发控件相邻。\n",
    },
  },
  {
    title: "订单回调：排查重复扣减库存",
    type: "缺陷修复",
    stack: 2,
    difficulty: "中等",
    duration: 75,
    repo: "order-service",
    entry: "app/payments.py",
    description:
      "支付网关会在未收到确认时重发回调。运营发现同一订单被重复扣减库存。根据事故日志追踪回调链路，修复幂等与失败恢复，并补充回归测试。",
    requirements: [
      "同一支付事件重复投递时，订单只完成一次，库存只扣减一次。",
      "不同事件重复通知同一订单也不得重复扣减；未知订单和金额不符的事件应拒绝。",
      "扣库存失败时不记录成功；再次投递可以重新处理。并发保障方案写入交付说明。",
    ],
    cases: [
      ["连续投递两次 evt-100 支付成功通知", "库存从 10 变为 8，订单变为 paid"],
      ["库存不足后补货并重投", "第一次失败不标记完成，重投成功且只扣一次"],
      ["订单应付 9900 分，回调金额为 99 分", "拒绝回调且订单与库存不变"],
    ],
    code: `from app.repository import Store

def handle_paid(store: Store, event: dict):
    order = store.orders[event['order_id']]
    store.stock[order['sku']] -= order['quantity']
    order['status'] = 'paid'
    store.events.add(event['id'])
    return {'accepted': True}
`,
    test: `import pytest
from app.repository import Store
from app.payments import handle_paid

def test_repeated_callback():
    store = Store()
    event = {'id': 'evt-100', 'order_id': 'O-1', 'amount': 9900}
    handle_paid(store, event)
    handle_paid(store, event)
    assert store.stock['book'] == 8

def test_wrong_amount_keeps_stock():
    store = Store()
    with pytest.raises(ValueError):
        handle_paid(store, {'id': 'evt-101', 'order_id': 'O-1', 'amount': 99})
    assert store.stock['book'] == 10
`,
    extra: {
      "app/repository.py": `class Store:
    def __init__(self):
        self.orders = {'O-1': {'sku': 'book', 'quantity': 2, 'amount': 9900, 'status': 'pending'}}
        self.stock = {'book': 10}
        self.events = set()
`,
      "docs/incident.log":
        "14:01:02 event=evt-100 order=O-1 status=200 stock=8\n14:01:04 event=evt-100 order=O-1 retry=1 status=200 stock=6\n",
      "docs/webhook.md":
        "# 支付事件\n金额单位：分。网关至少投递一次，事件可能重复或乱序。\n本仓库使用内存 Store；不要求接入真实数据库。并发事务设计需在说明中给出。\n",
    },
  },
  {
    title: "团队知识库：追踪越权访问",
    type: "代码理解",
    stack: 1,
    difficulty: "中等",
    duration: 60,
    repo: "team-wiki",
    entry: "src/documents.ts",
    description:
      "安全巡检发现成员可以通过文档 ID 读取其他团队的私有文档。阅读请求上下文、文档查询与权限模块，给出访问链路和根因，完成最小修复并验证兼容性。",
    requirements: [
      "在 ANALYSIS.md 描述请求入口、文档加载、权限判断的调用关系。",
      "私有文档只对同团队成员开放；公开文档允许已登录用户访问。",
      "未知 ID 返回未找到，跨团队访问返回无权限；不得仅在前端隐藏入口。",
    ],
    cases: [
      ["团队 A 成员读取团队 B 私有文档", "拒绝访问"],
      ["团队 A 成员读取团队 B 公开文档", "允许访问"],
      ["使用不存在的文档 ID", "返回未找到，不暴露其他文档信息"],
    ],
    code: `import { documents } from './repository';
import type { Actor } from './auth';
export function readDocument(id: string, actor: Actor) {
  if (!actor.id) throw new Error('unauthorized');
  const doc = documents.find(d => d.id === id);
  if (!doc) throw new Error('not_found');
  return doc;
}
`,
    test: `import { expect, it } from 'vitest';
import { readDocument } from '../src/documents';
it('blocks another team private document', () => {
  expect(() => readDocument('D-1', { id: 'u1', team: 'A' })).toThrow('forbidden');
});
it('allows public document', () => {
  expect(readDocument('D-2', { id: 'u1', team: 'A' }).id).toBe('D-2');
});
`,
    extra: {
      "src/auth.ts": "export type Actor = { id: string; team: string };\n",
      "src/repository.ts":
        "export const documents = [{ id: 'D-1', team: 'B', public: false, text: '内部计划' }, { id: 'D-2', team: 'B', public: true, text: '公开手册' }];\n",
      "ANALYSIS.md": "# 访问链路\n\n# 根因与影响范围\n\n# 修复选择与验证\n",
    },
  },
  {
    title: "通知中心：拆分渠道与重试策略",
    type: "工程重构",
    stack: 1,
    difficulty: "困难",
    duration: 100,
    repo: "notification-center",
    entry: "src/notify.ts",
    description:
      "通知服务把渠道分支、重试与日志写在同一函数中，新增渠道经常破坏已有行为。将其重构为可替换的渠道适配器与调度流程，保留原有调用接口。",
    requirements: [
      "保留 notify(channel, message, send) 接口，支持 email 和 sms，未知渠道立即失败。",
      "只重试暂时性失败，最多三次；永久性失败不重试。",
      "每次尝试记录渠道与次数，避免在日志中记录消息正文。",
    ],
    cases: [
      ["发送前两次暂时失败，第三次成功", "调用三次并返回成功"],
      ["发送抛出永久失败", "只调用一次并返回失败"],
      ["传入未知渠道", "发送器不被调用"],
    ],
    code: `export async function notify(channel: string, message: string, send: (text: string) => Promise<void>) {
  if (channel !== 'email' && channel !== 'sms') throw new Error('unknown channel');
  for (let attempt = 1; attempt <= 3; attempt++) {
    try { await send(message); return { delivered: true, attempts: attempt }; }
    catch (error) { console.log(channel, message, error); }
  }
  return { delivered: false, attempts: 3 };
}
`,
    test: `import { expect, it, vi } from 'vitest';
import { notify } from '../src/notify';
it('does not retry permanent errors', async () => {
  const send = vi.fn().mockRejectedValue(Object.assign(new Error('invalid address'), { permanent: true }));
  await notify('email', 'hello', send);
  expect(send).toHaveBeenCalledTimes(1);
});
`,
  },
  {
    title: "报销审批：实现角色与金额规则",
    type: "需求实现",
    stack: 2,
    difficulty: "中等",
    duration: 90,
    repo: "expense-workflow",
    entry: "app/approval.py",
    description:
      "现有报销服务可以创建申请，缺少审批流程。根据财务规则补全审批权限、状态流转和审计记录，让每次决策都能追溯。",
    requirements: [
      "金额不超过 5000 元由经理审批，超过 5000 元还需财务复核。",
      "申请人不能审批自己的申请，已完成或已拒绝的申请不可重复审批。",
      "拒绝必须填写原因，每次合法决策记录操作人、动作和审批前后状态。",
    ],
    cases: [
      ["经理批准 6000 元申请", "进入财务待审，财务批准后完成"],
      ["申请人审批自己的报销", "拒绝且无状态变更"],
      ["同一审批重复发送", "不产生重复审计记录"],
    ],
    code: `def approve(expense, actor, decision, reason=''):
    updated = dict(expense)
    updated['status'] = 'approved' if decision == 'approve' else 'rejected'
    return updated
`,
    test: `import pytest
from app.approval import approve

def test_large_amount_requires_finance():
    expense = {'id': 'E-1', 'owner': 'lin', 'amount': 6000, 'status': 'pending', 'audit': []}
    result = approve(expense, {'id': 'chen', 'role': 'manager'}, 'approve')
    assert result['status'] == 'finance_pending'
`,
    extra: {
      "docs/policy.md":
        "# 审批角色\nmanager：经理；finance：财务。\n金额采用整数元。无须接入真实登录，actor 由可信上游传入。\n",
    },
  },
  {
    title: "搜索面板：修复异步结果覆盖",
    type: "缺陷修复",
    stack: 0,
    difficulty: "中等",
    duration: 75,
    repo: "customer-search",
    entry: "src/search.ts",
    description:
      "客户搜索面板在快速输入时偶尔显示旧关键词结果，清空输入后仍会出现列表。重现竞态问题，修改请求管理，并验证加载与错误状态。",
    requirements: [
      "只有最新关键词对应的请求可以更新列表、错误和加载状态。",
      "清空关键词时立即清空列表；旧请求完成后不得恢复旧结果。",
      "销毁面板后取消未完成请求，错误不应导致 loading 长期为 true。",
    ],
    cases: [
      ["依次搜索 a 和 ab，ab 先返回", "最终只显示 ab 的结果"],
      ["请求期间清空搜索框", "列表为空且加载结束"],
      ["最新请求失败后重新搜索", "显示错误，重试成功后清除错误"],
    ],
    code: `export function createSearch(fetcher: (q: string, signal?: AbortSignal) => Promise<string[]>) {
  const state = { items: [] as string[], loading: false, error: '' };
  async function search(q: string) {
    state.loading = true;
    state.items = await fetcher(q);
    state.loading = false;
  }
  return { state, search, dispose() {} };
}
`,
    test: `import { expect, it } from 'vitest';
import { createSearch } from '../src/search';
it('keeps the newest response', async () => {
  let resolveA!: (v: string[]) => void;
  const controller = createSearch(q => q === 'a' ? new Promise(r => resolveA = r) : Promise.resolve(['ab']));
  const first = controller.search('a');
  await controller.search('ab');
  resolveA(['a']); await first;
  expect(controller.state.items).toEqual(['ab']);
});
`,
    extra: {
      "src/App.vue": `<script setup lang="ts">
import { reactive, onUnmounted } from 'vue';
import { createSearch } from './search';
const search = createSearch(async (q, signal) => { const response = await fetch('/api/customers?q=' + encodeURIComponent(q), { signal }); return response.json(); });
const state = reactive(search.state);
onUnmounted(() => search.dispose());
</script>
<template><main><h1>客户搜索</h1><input aria-label="搜索客户" @input="search.search(($event.target as HTMLInputElement).value)" /><p v-if="state.loading">加载中</p><p>{{ state.error }}</p><ul><li v-for="item in state.items" :key="item">{{ item }}</li></ul></main></template>
`,
    },
  },
  {
    title: "文件导入：定位数据丢失链路",
    type: "代码理解",
    stack: 2,
    difficulty: "简单",
    duration: 60,
    repo: "contact-importer",
    entry: "app/importer.py",
    description:
      "运营导入 100 行联系人后，只看到 86 行数据。阅读清洗、去重、写入三个阶段，解释哪些数据被丢弃，建立可核对的导入结果报告。",
    requirements: [
      "画清导入流水线并在 ANALYSIS.md 说明每一阶段的数据变化。",
      "按规范化后的邮箱去重；无效行和重复行需分别报告行号与原因。",
      "所有输入行必须归入成功、重复或无效，三类数量之和等于输入数量。",
    ],
    cases: [
      ["导入大小写不同的相同邮箱", "一行成功、一行重复"],
      ["姓名为空或邮箱无 @", "报告原始行号与无效原因"],
      ["导入混合有效与无效数据", "统计总数可以对账，成功行保持原顺序"],
    ],
    code: `from app.normalize import normalize

def import_contacts(rows):
    seen = set()
    saved = []
    for row in rows:
        contact = normalize(row)
        if not contact or contact['email'] in seen:
            continue
        seen.add(contact['email'])
        saved.append(contact)
    return {'saved': saved}
`,
    test: `from app.importer import import_contacts

def test_import_is_reconcilable():
    result = import_contacts([{'name': 'Lin', 'email': 'A@EXAMPLE.COM'}, {'name': 'Lin', 'email': 'a@example.com'}, {'name': '', 'email': 'bad'}])
    assert len(result['saved']) == 1
    assert len(result['duplicates']) == 1
    assert result['invalid'][0]['line'] == 3
`,
    extra: {
      "app/normalize.py":
        "def normalize(row):\n    name = row.get('name', '').strip()\n    email = row.get('email', '').strip().lower()\n    if not name or '@' not in email: return None\n    return {'name': name, 'email': email}\n",
      "ANALYSIS.md": "# 流水线\n\n# 数据丢失原因\n\n# 对账规则\n",
    },
  },
  {
    title: "计费模块：拆分折扣与审计",
    type: "工程重构",
    stack: 2,
    difficulty: "困难",
    duration: 100,
    repo: "billing-core",
    entry: "app/billing.py",
    description:
      "计费函数同时负责会员折扣、优惠券、金额计算与记录日志。保持既有价格规则，拆分纯计算与副作用，使后续新增促销规则可独立测试。",
    requirements: [
      "会员九折后再减固定优惠券，最低应付为零，金额使用整数分。",
      "计算函数不修改订单、用户或外部日志；审计由独立入口写入。",
      "保持 bill(order, user, coupon, audit) 接口；说明新模块边界与迁移风险。",
    ],
    cases: [
      ["10000 分订单，会员折扣加 1000 分券", "应付 8000 分"],
      ["连续调用相同参数两次", "价格一致，原订单金额不变"],
      ["优惠券超过折后金额", "应付为零，审计只记录必要字段"],
    ],
    code: `def bill(order, user, coupon, audit):
    if user.get('member'):
        order['amount'] = order['amount'] * 90 // 100
    total = max(0, order['amount'] - coupon)
    audit.append({'order': order['id'], 'amount': total, 'user': user})
    return total
`,
    test: `from app.billing import bill

def test_repeated_calculation_does_not_mutate_order():
    order = {'id': 'O-1', 'amount': 10000}
    user = {'id': 'u1', 'member': True}
    assert bill(order, user, 1000, []) == 8000
    assert bill(order, user, 1000, []) == 8000
    assert order['amount'] == 10000
`,
  },
  {
    title: "活动报名：增加候补与取消机制",
    type: "需求实现",
    stack: 1,
    difficulty: "困难",
    duration: 120,
    repo: "event-booking",
    entry: "src/booking.ts",
    description:
      "校园活动服务只有简单报名接口，满额后无法安排候补。扩展现有报名模型，支持候补队列、取消与自动补位，并解释并发控制方案。",
    requirements: [
      "有空位时确认报名，满额时加入候补；同一成员只保留一个有效报名。",
      "已确认成员取消后，最早候补自动补位；候补取消不影响名额。",
      "报名与取消可以安全重试，人数不得超过容量；说明数据库事务与唯一约束设计。",
    ],
    cases: [
      ["容量 1，依次报名 A 和 B", "A 已确认，B 候补"],
      ["A 取消报名", "B 自动成为已确认"],
      ["同一成员重复报名或重复取消", "无重复报名且名额统计准确"],
    ],
    code: `export type Booking = { user: string; status: 'confirmed' | 'waiting' | 'cancelled' };
export function register(bookings: Booking[], user: string, capacity: number): Booking[] {
  return [...bookings, { user, status: 'confirmed' }];
}
export function cancel(bookings: Booking[], user: string): Booking[] {
  return bookings.filter(b => b.user !== user);
}
`,
    test: `import { expect, it } from 'vitest';
import { register, cancel } from '../src/booking';
it('promotes the first waiting attendee', () => {
  const first = register([], 'A', 1);
  const full = register(first, 'B', 1);
  expect(full[1].status).toBe('waiting');
  expect(cancel(full, 'A').find(b => b.user === 'B')?.status).toBe('confirmed');
});
`,
  },
  {
    title: "API 客户端：修复超时重试与取消",
    type: "缺陷修复",
    stack: 1,
    difficulty: "困难",
    duration: 90,
    repo: "api-client",
    entry: "src/client.ts",
    description:
      "客户端在用户取消操作后仍会继续重试，部分创建订单请求还被重复执行。修复重试边界，统一取消与错误传播，验证请求次数。",
    requirements: [
      "只对 GET 的网络错误与 5xx 重试，最多三次；POST 不自动重试。",
      "外部 AbortSignal 取消后立即停止，不再发起请求。",
      "4xx、取消、重试耗尽分别保留可辨认的错误，定时器和监听器必须释放。",
    ],
    cases: [
      ["GET 连续两次 503，第三次 200", "请求三次后成功"],
      ["POST 返回 503", "只请求一次并报告失败"],
      ["首次请求期间取消", "停止请求且不发生后续重试"],
    ],
    code: `export async function request(url: string, options: RequestInit = {}, fetcher = fetch): Promise<Response> {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetcher(url, options);
      if (response.ok) return response;
    } catch {}
  }
  throw new Error('request failed');
}
`,
    test: `import { expect, it, vi } from 'vitest';
import { request } from '../src/client';
it('does not retry POST', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 503 }));
  await expect(request('/orders', { method: 'POST' }, fetcher)).rejects.toThrow();
  expect(fetcher).toHaveBeenCalledTimes(1);
});
`,
  },
  {
    title: "发布平台：分析回滚与版本选择",
    type: "代码理解",
    stack: 1,
    difficulty: "中等",
    duration: 60,
    repo: "release-console",
    entry: "src/releases.ts",
    description:
      "发布平台点回滚后切换到了其他环境的版本。阅读发布记录、目标筛选和回滚调用，解释错误如何发生并修正目标选择。",
    requirements: [
      "在 ANALYSIS.md 写出从回滚入口到目标版本选择的路径与根因。",
      "只能选择同服务、同环境、时间早于当前版本的成功发布。",
      "选取最近一次合法发布；没有候选时返回明确错误且不触发部署。",
    ],
    cases: [
      ["生产版本之后存在测试环境成功发布", "回滚仍选择生产环境历史版本"],
      ["最近一次历史发布失败", "跳过失败记录"],
      ["首次生产发布请求回滚", "报告没有可回滚版本"],
    ],
    code: `export type Release = { id: string; service: string; env: string; time: number; status: string };
export function rollbackTarget(current: Release, history: Release[]) {
  return [...history].sort((a, b) => b.time - a.time)[0];
}
`,
    test: `import { expect, it } from 'vitest';
import { rollbackTarget } from '../src/releases';
it('selects a previous successful release in the same environment', () => {
  const current = { id: 'r3', service: 'api', env: 'prod', time: 3, status: 'success' };
  const history = [{ ...current, id: 'r1', time: 1 }, { ...current, id: 'r2', env: 'test', time: 2 }];
  expect(rollbackTarget(current, history)?.id).toBe('r1');
});
`,
    extra: {
      "ANALYSIS.md": "# 调用链\n\n# 根因与影响范围\n\n# 修复方案与验证\n",
    },
  },
  {
    title: "数据看板：重构统计逻辑与展示",
    type: "工程重构",
    stack: 0,
    difficulty: "中等",
    duration: 90,
    repo: "sales-dashboard",
    entry: "src/metrics.ts",
    description:
      "销售看板在多个组件中重复计算统计指标，切换筛选会修改共享数据。抽离可测试的统计层，让组件只负责展示与交互。",
    requirements: [
      "按所选月份统计已支付订单，排除退款订单；金额统一为整数分。",
      "统计函数不修改原始订单，不依赖 Vue 或浏览器环境。",
      "保留月份筛选与空状态，补充跨月边界、退款和重复计算的测试。",
    ],
    cases: [
      ["同月包含已支付与已退款订单", "只统计已支付订单"],
      ["切换月份后再次切回", "原数据未被改变，统计一致"],
      ["所选月份无订单", "数量和金额均为零，显示空状态"],
    ],
    code: `export type Order = { id: string; month: string; status: 'paid' | 'refunded'; amount: number };
export function summarize(orders: Order[], month: string) {
  orders.sort((a, b) => b.amount - a.amount);
  const visible = orders.filter(order => order.month === month);
  return { count: visible.length, total: visible.reduce((n, order) => n + order.amount, 0) };
}
`,
    test: `import { expect, it } from 'vitest';
import { summarize } from '../src/metrics';
it('excludes refunds', () => {
  expect(summarize([{ id: '1', month: '2026-10', status: 'paid', amount: 9900 }, { id: '2', month: '2026-10', status: 'refunded', amount: 8800 }], '2026-10')).toEqual({ count: 1, total: 9900 });
});
`,
    extra: {
      "src/App.vue": `<script setup lang="ts">
import { computed, ref } from 'vue';
import { summarize, type Order } from './metrics';
const month = ref('2026-10');
const orders: Order[] = [{ id: '1', month: '2026-10', status: 'paid', amount: 9900 }, { id: '2', month: '2026-10', status: 'refunded', amount: 8800 }];
const metrics = computed(() => summarize(orders, month.value));
</script>
<template><main><h1>销售概览</h1><input type="month" v-model="month" aria-label="月份" /><p>{{ metrics.count }} 笔订单 · {{ (metrics.total / 100).toFixed(2) }} 元</p></main></template>
`,
    },
  },
];

export const problems: Problem[] = entries.map((e, i) => {
  const python = e.stack === 2,
    vue = e.stack === 0;
  const commands = python
    ? {
        setup: "python -m pip install -r requirements.txt",
        test: "python -m pytest -q",
        start: "",
      }
    : {
        setup: "npm install",
        test: "npm test",
        start: vue ? "npm run dev" : "",
      };
  const deliverables = [
    "项目代码与测试",
    e.type === "代码理解" ? "调用链与根因分析" : "变更说明与设计取舍",
    "AI 协作与验证记录",
  ];
  const files: ProjectFiles = {
    "README.md": `# ${e.repo}\n\n${e.description}\n\n## 开发\n${commands.setup}\n${commands.test}\n${commands.start}\n\n## 任务\n${e.requirements.map((r, n) => `${n + 1}. ${r}`).join("\n")}\n`,
    [e.entry]: e.code,
    [python ? "tests/test_project.py" : "tests/project.test.ts"]: e.test,
    "CHANGELOG.md":
      "# 变更说明\n\n## 需求拆解\n\n## 设计与取舍\n\n## 验证结果\n\n## AI 建议的采纳与核验\n",
    ...e.extra,
  };
  if (python) {
    files["app/__init__.py"] = "";
    files["requirements.txt"] = "pytest==8.3.5\n";
    files["pyproject.toml"] =
      '[tool.pytest.ini_options]\npythonpath = ["."]\ntestpaths = ["tests"]\n';
  } else {
    files["package.json"] = JSON.stringify(
      {
        name: e.repo,
        private: true,
        type: "module",
        scripts: { test: "vitest run", ...(vue ? { dev: "vite" } : {}) },
        devDependencies: {
          vitest: "3.2.4",
          typescript: "5.9.3",
          ...(vue
            ? { vite: "7.1.12", "@vitejs/plugin-vue": "6.0.1", vue: "3.5.22" }
            : {}),
        },
      },
      null,
      2,
    );
    files["tsconfig.json"] = JSON.stringify(
      {
        compilerOptions: {
          target: "ES2022",
          module: "ESNext",
          moduleResolution: "bundler",
          strict: true,
          lib: ["ES2022", "DOM"],
        },
        include: ["src", "tests"],
      },
      null,
      2,
    );
    if (vue) {
      files["index.html"] =
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>' +
        e.repo +
        '</title></head><body><div id="app"></div><script type="module" src="/src/main.ts"></script></body></html>';
      files["src/main.ts"] =
        "import { createApp } from 'vue';\nimport App from './App.vue';\ncreateApp(App).mount('#app');\n";
      files["vite.config.ts"] =
        "import { defineConfig } from 'vite';\nimport vue from '@vitejs/plugin-vue';\nexport default defineConfig({ plugins: [vue()] });\n";
    }
  }
  return {
    id: `E${1001 + i}`,
    title: e.title,
    type: e.type,
    difficulty: e.difficulty,
    tags: [
      e.type,
      [
        "状态流转",
        "幂等处理",
        "访问控制",
        "适配器设计",
        "审批规则",
        "异步竞态",
        "数据追踪",
        "模块拆分",
        "并发一致性",
        "重试策略",
        "变更分析",
        "职责分离",
      ][i],
      python ? "Python" : vue ? "Vue" : "TypeScript",
    ],
    description: e.description,
    stack: stacks[e.stack],
    duration: e.duration,
    repository: e.repo,
    entryFile: e.entry,
    files,
    requirements: e.requirements,
    acceptance: e.cases.map(([scenario, expected], n) => ({
      id: `AC-${n + 1}`,
      scenario,
      expected,
    })),
    constraints: [
      "保留现有公开接口与已提供的测试。",
      "使用仓库已有依赖；新增依赖需说明理由。",
      "提交代码、测试及验证记录。",
    ],
    deliverables,
    commands,
    evaluation: { timeout: 120, memory: 1024, network: "依赖白名单" },
    solved: [1, 6].includes(i),
    attempts: 268 - i * 13,
    passRate: 76 - i * 2,
    version: "v2.0",
    bank: "内置题库",
    status: "已发布",
    source: "课程小组原创工程场景",
    weights: [...defaultWeights],
  };
});
export const seedExams: Exam[] = [
  {
    id: "exam-1",
    title: "AI Coding · 工单协作台功能迭代",
    start: "2026-10-31T06:00:00Z",
    end: "2026-10-31T08:00:00Z",
    status: "进行中",
    problemIds: ["E1001"],
    weights: [100],
    published: false,
  },
  {
    id: "exam-2",
    title: "工程诊断 · 代码理解与缺陷修复",
    start: "2026-11-04T06:00:00Z",
    end: "2026-11-04T08:30:00Z",
    status: "已发布",
    problemIds: ["E1003", "E1010"],
    weights: [40, 60],
    published: false,
  },
  {
    id: "exam-3",
    title: "AI Coding · 订单回调故障排查",
    start: "2026-10-24T06:00:00Z",
    end: "2026-10-24T07:30:00Z",
    status: "成绩已发布",
    problemIds: ["E1002"],
    weights: [100],
    published: true,
  },
].map((e) => ({
  ...e,
  status: e.status as Exam["status"],
  className: "示例班级",
  model: "course-coder-v1",
  requests: 40,
  tokens: 60000,
  personal: false,
  leaderboard: true,
  aiContext: "项目文件",
  aiMode: "对话与代码建议",
  deliverables: ["项目代码与测试", "变更说明", "AI 协作与验证记录"],
  snapshots: JSON.parse(
    JSON.stringify(problems.filter((p) => e.problemIds.includes(p.id))),
  ),
}));
export const seedSubmissions: Submission[] = [
  {
    id: "SUB-ENGINEERING-001",
    problemId: "E1002",
    userId: "u-student",
    files: { ...problems[1].files },
    problemSnapshot: problems[1],
    explanation:
      "追踪回调 → 订单查询 → 库存扣减。设计事件去重、订单状态检查与失败回滚，使用重复通知和金额不符场景验证。",
    status: "COMPLETED",
    createdAt: "2026-10-24T07:20:00Z",
    scores: [90, 80, 80, 70, 60, 80],
    version: 1,
    idempotencyKey: "engineering-seed-1",
  },
];
export const seedClasses: import("./types").ClassRoom[] = [
  {
    id: "class-1",
    name: "示例班级",
    teacher: "陈老师",
    code: "SE2026",
    archived: false,
    members: [
      { id: "u-student", name: "林同学", joined: "2026-09-01" },
      { id: "20230002", name: "陈同学", joined: "2026-09-02" },
      { id: "20230003", name: "周同学", joined: "2026-09-02" },
      { id: "20230004", name: "李同学", joined: "2026-09-03" },
    ],
  },
];
