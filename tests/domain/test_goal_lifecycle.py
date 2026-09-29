"""Goal lifecycle through ordinary task commands, using a real isolated database."""
import uuid

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain import commands as tasks, goals
from local_planner.domain.errors import Conflict, NotFound
from local_planner.domain.seal import seal_day
from local_planner.domain.undo import delete_with_undo, undo_delete
from local_planner.persistence.store import SqliteUnitOfWork

TODAY = '2026-09-28'
FUTURE = '2026-09-30'


@pytest.fixture
def env(tmp_path):
    clock = FrozenClock(TODAY + 'T12:00:00+08:00')
    uow = SqliteUnitOfWork.open(tmp_path / 'goals.sqlite')
    yield clock, uow
    uow.close()


def call(env, fn, *args, **kwargs):
    clock, uow = env
    with uow.transaction():
        return fn(clock, uow, *args, **kwargs)


def new(env, title='通过 CSP 认证'):
    return call(env, goals.create_goal, title, horizon_text='2027 年', request_id=str(uuid.uuid4()))


def change(env, goal, op, **values):
    current = env[1].get_goal(goal.id)
    return call(env, goals.change_goal, goal.id, op, expected_revision=current.revision, **values)


def action(env, goal, title='做一道基础题', **kwargs):
    old = {t.id for t in env[1].list_goal_tasks(goal.id)}
    change(env, goal, 'add-task', title=title, request_id=str(uuid.uuid4()), **kwargs)
    return next(t for t in env[1].list_goal_tasks(goal.id) if t.id not in old)


def choose(env, goal, task):
    return change(env, goal, 'next', task_id=task.id)


def test_goal_task_is_same_task_when_scheduled_and_rolled_back_to_inventory(env):
    clock, uow = env
    g = new(env)
    t = action(env, g, notes='先尝试，再看题解')
    choose(env, g, t)
    change(env, g, 'schedule-next', expected_task_id=t.id, expected_scheduled_date=None)
    assert uow.get_task(t.id).goal_id == g.id
    assert uow.get_entry(TODAY, t.id).goal_title_snapshot == g.title
    assert uow.get_entry(TODAY, t.id).notes_snapshot == t.notes
    call(env, seal_day, TODAY)
    clock.set('2026-09-29T09:00:00+08:00')
    assert uow.get_task(t.id).current_scheduled_date is None
    assert uow.get_goal(g.id).next_task_id == t.id
    assert [x.id for x in uow.list_inventory_tasks()] == [t.id]
    change(env, g, 'schedule-next', expected_task_id=t.id, expected_scheduled_date=None)
    assert uow.get_entry('2026-09-29', t.id).goal_id_snapshot == g.id


def test_future_next_move_preserves_clock_notes_id_and_reports_conflict_for_stale_location(env):
    _, uow = env
    g = new(env); t = action(env, g, notes='两行\n备注')
    choose(env, g, t)
    call(env, tasks.schedule_to_date, t.id, FUTURE)
    call(env, tasks.set_plan_clocks, FUTURE, t.id, '09:00', '10:00')
    with pytest.raises(Conflict):
        change(env, g, 'schedule-next', expected_task_id=t.id, expected_scheduled_date=None)
    assert uow.get_task(t.id).current_scheduled_date == FUTURE
    change(env, g, 'schedule-next', expected_task_id=t.id, expected_scheduled_date=FUTURE)
    entry = uow.get_entry(TODAY, t.id)
    assert (entry.start_clock, entry.end_clock, entry.notes_snapshot) == ('09:00','10:00',t.notes)
    assert uow.get_entry(FUTURE, t.id) is None
    # Already today is a harmless read, with no revision bump.
    revision = uow.get_goal(g.id).revision
    change(env, g, 'schedule-next', expected_task_id=t.id, expected_scheduled_date=TODAY)
    assert uow.get_goal(g.id).revision == revision


@pytest.mark.parametrize('completed_from', ['inventory', 'today'])
def test_completing_goal_action_clears_next_but_does_not_complete_goal(env, completed_from):
    _, uow = env
    g = new(env); t = action(env, g); choose(env, g, t)
    revision = uow.get_goal(g.id).revision
    if completed_from == 'inventory':
        call(env, tasks.complete_inventory_task, t.id)
    else:
        call(env, tasks.schedule_to_date, t.id, TODAY)
        call(env, tasks.complete_task_on_day, t.id, TODAY)
    assert uow.get_goal(g.id).next_task_id is None
    assert uow.get_goal(g.id).state == 'active'
    assert uow.get_goal(g.id).revision > revision
    assert uow.get_task(t.id).goal_id == g.id
    t2 = action(env, g, '第二题'); choose(env, g, t2)
    call(env, tasks.uncomplete_task_on_day, t.id, TODAY)
    assert uow.get_goal(g.id).next_task_id == t2.id


@pytest.mark.parametrize('new_selection', [False, True])
def test_delete_undo_restores_link_without_overwriting_new_next(env, new_selection):
    _, uow = env
    g = new(env); t = action(env, g); t2 = action(env, g, '另外一步'); choose(env, g, t)
    deleted = call(env, delete_with_undo, 'task', t.id)
    assert uow.get_task(t.id) is None
    assert not any(item.task_id == t.id for item in uow.list_goal_actions(g.id))
    assert uow.get_goal(g.id).next_task_id is None
    if new_selection: choose(env, g, t2)
    call(env, undo_delete, deleted)
    assert uow.get_task(t.id).goal_id == g.id
    assert any(item.task_id == t.id for item in uow.list_goal_actions(g.id))
    assert uow.get_goal(g.id).next_task_id == (t2.id if new_selection else t.id)


def test_discard_after_rollover_clears_next_and_undo_preserves_snapshot(env):
    clock,uow = env
    g = new(env); t = action(env,g); choose(env,g,t)
    call(env,tasks.schedule_to_date,t.id,TODAY)
    call(env,seal_day,TODAY); clock.set('2026-09-29T12:00:00+08:00')
    old = uow.get_entry(TODAY,t.id)
    deleted = call(env,delete_with_undo,'task',t.id)
    assert uow.get_task(t.id).discarded_at is not None
    assert uow.get_goal(g.id).next_task_id is None
    with pytest.raises(NotFound): call(env,tasks.schedule_to_date,t.id,FUTURE)
    call(env,undo_delete,deleted)
    assert uow.get_task(t.id).discarded_at is None
    assert uow.get_entry(TODAY,t.id) == old


def test_goal_and_phase_rename_only_update_open_snapshots(env):
    clock,uow = env
    g = new(env)
    change(env,g,'add-phase',title='基础',request_id='phase')
    phase = uow.list_phases(g.id)[0]
    t = action(env,g,phase_id=phase.id)
    call(env,tasks.schedule_to_date,t.id,TODAY)
    call(env,seal_day,TODAY); clock.set('2026-09-29T12:00:00+08:00')
    before = uow.get_entry(TODAY,t.id)
    call(env,tasks.schedule_to_date,t.id,FUTURE)
    change(env,g,'edit',title='新的目标',notes='',horizon_text='明年春天')
    change(env,g,'edit-phase',phase_id=phase.id,title='进阶',notes='',status='open')
    assert uow.get_entry(TODAY,t.id) == before
    future = uow.get_entry(FUTURE,t.id)
    assert (future.goal_title_snapshot,future.phase_title_snapshot) == ('新的目标','进阶')


@pytest.mark.parametrize('state,reason',[('paused',None),('ended','achieved'),('ended','abandoned')])
def test_pause_end_reopen_never_cascades_to_scheduled_tasks(env,state,reason):
    _,uow = env
    g = new(env); t = action(env,g); choose(env,g,t)
    call(env,tasks.schedule_to_date,t.id,FUTURE)
    before = uow.get_task(t.id)
    change(env,g,'state',state=state,end_reason=reason)
    assert uow.get_task(t.id) == before
    assert uow.get_goal(g.id).next_task_id == t.id
    with pytest.raises(Conflict):
        change(env,g,'schedule-next',expected_task_id=t.id,expected_scheduled_date=FUTURE)
    change(env,g,'state',state='active',end_reason=None)
    assert uow.get_task(t.id) == before


def test_sql_transaction_rolls_back_partial_goal_operation(env):
    _,uow = env
    g = new(env)
    with pytest.raises(RuntimeError):
        with uow.transaction():
            goals.change_goal(env[0],uow,g.id,'add-task',expected_revision=g.revision,title='不会留下',request_id='retry')
            raise RuntimeError('simulate failure before commit')
    assert uow.list_goal_tasks(g.id) == []
    assert uow.get_goal(g.id) == g
    assert uow.get_goal_request('retry') is None
    change(env,g,'add-task',title='不会留下',request_id='retry')
    assert len(uow.list_goal_tasks(g.id)) == 1


def test_unlink_keeps_task_schedule_but_removes_goal_context_on_open_day(env):
    _,uow=env
    g=new(env);t=action(env,g);choose(env,g,t)
    call(env,tasks.schedule_to_date,t.id,TODAY)
    change(env,g,'unlink-task',task_id=t.id)
    assert uow.get_task(t.id).current_scheduled_date == TODAY
    assert uow.get_task(t.id).goal_id is None
    assert uow.get_entry(TODAY,t.id).goal_title_snapshot is None
    assert uow.get_goal(g.id).next_task_id is None


def test_cas_prevents_stale_goal_draft_after_normal_task_change(env):
    _,uow=env
    g=new(env);t=action(env,g);g=uow.get_goal(g.id)
    call(env,tasks.rename_task,t.id,'改过的标题')
    with pytest.raises(Conflict):
        call(env,goals.change_goal,g.id,'edit',expected_revision=g.revision,title='覆盖',notes='',horizon_text='')
    assert uow.get_goal(g.id).title == g.title


def test_cross_goal_link_and_phase_assignment_rejected_without_mutation(env):
    _,uow=env
    g=new(env); other=new(env,'另一个目标');t=action(env,g)
    change(env,other,'add-phase',title='其他目标的阶段',request_id='other-phase')
    p=uow.list_phases(other.id)[0]
    before=uow.get_goal(g.id)
    with pytest.raises(Conflict):
        change(env,other,'link-task',task_id=t.id,phase_id=None,expected_goal_id=g.id)
    from local_planner.domain.errors import ValidationError
    with pytest.raises(ValidationError):
        change(env,g,'link-task',task_id=t.id,phase_id=p.id,expected_goal_id=g.id)
    assert uow.get_task(t.id).goal_id == g.id
    assert uow.get_goal(g.id) == before


@pytest.mark.parametrize('status',['done','skipped'])
def test_closed_phase_does_not_offer_next_until_reopened(env,status):
    _,uow=env
    g=new(env);change(env,g,'add-phase',title='准备',request_id='p')
    p=uow.list_phases(g.id)[0];t=action(env,g,phase_id=p.id);choose(env,g,t)
    change(env,g,'focus-phase',phase_id=p.id)
    call(env,tasks.schedule_to_date,t.id,FUTURE)
    before=uow.get_task(t.id)
    change(env,g,'edit-phase',phase_id=p.id,title=p.title,notes='',status=status)
    assert uow.get_task(t.id) == before
    assert uow.get_goal(g.id).focus_phase_id is None
    assert uow.get_goal(g.id).next_task_id is None
    with pytest.raises(Conflict):choose(env,g,t)
    with pytest.raises(Conflict):change(env,g,'focus-phase',phase_id=p.id)
    change(env,g,'edit-phase',phase_id=p.id,title=p.title,notes='',status='open')
    choose(env,g,t)
    assert uow.get_goal(g.id).next_task_id == t.id


def test_phase_reorder_requires_whole_current_membership(env):
    _,uow=env;g=new(env)
    for i in range(3):change(env,g,'add-phase',title=f'阶段{i}',request_id=f'p{i}')
    ids=[p.id for p in uow.list_phases(g.id)]
    for bad in [ids[:-1],ids+[ids[0]],ids[:-1]+['missing']]:
        with pytest.raises(Conflict):change(env,g,'reorder-phases',phase_ids=bad)
        assert [p.id for p in uow.list_phases(g.id)] == ids
    change(env,g,'reorder-phases',phase_ids=ids[::-1])
    assert [p.id for p in uow.list_phases(g.id)] == ids[::-1]


def test_association_of_recurrence_occurrence_does_not_bind_whole_series(env):
    _,uow=env;g=new(env)
    series=call(env,tasks.create_recurrence,kind='plan',title='每天练习',frequency='daily',start_date=TODAY,weekdays=None)
    today=call(env,tasks.open_day,TODAY)
    t=uow.get_task(today.todos[0].task_id)
    change(env,g,'link-task',task_id=t.id,expected_goal_id=None,phase_id=None)
    future=call(env,tasks.open_day,FUTURE)
    assert uow.get_task(future.todos[0].task_id).goal_id is None
    assert uow.get_task(t.id).goal_id == g.id
    assert uow.get_recurrence(series.id) == series
