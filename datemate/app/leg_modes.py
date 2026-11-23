"""구간별 이동 수단.

코스 전체의 기본 수단(conditions.transport)은 그대로 두고, 바꾼 구간만 conditions.leg_modes에
{from, to, mode}로 남긴다. 구간은 출발('origin' 또는 장소 id)과 도착(장소 id 또는 'home')으로
찾으므로 장소를 바꾸면 그 앞뒤 구간은 저절로 기본 수단으로 돌아간다.

차 위치는 계산에 넣지 않는다. car_position_notes()가 정해진 규칙으로 안내만 만든다.
"""

from .models import Conditions

MODES = ('walk', 'transit', 'car', 'bicycle')
NAMES = {'walk': '도보', 'transit': '대중교통', 'car': '자동차', 'bicycle': '자전거'}
MAX_ROUTE_CALLS = 6


def josa(word, with_final, without_final):
    """받침이 있으면 with_final(을/이/은), 없으면 without_final(를/가/는)."""
    last = str(word or '').strip()[-1:]
    if '가' <= last <= '힣':
        return with_final if (ord(last) - 0xAC00) % 28 else without_final
    if last.isdigit():  # 영·일·삼·육·칠·팔은 받침이 있고 이·사·오·구는 없다.
        return with_final if last in '013678' else without_final
    return with_final + '(' + without_final + ')' if last else with_final


def uses_car(c):
    """기본 수단이나 예외 중 하나라도 자동차인지."""
    return c.transport == 'car' or any(m.mode == 'car' for m in c.leg_modes)


def middle_after(plan):
    """코스 중간에 둔 축제(festival_visit.position 'middle')의 앞 장소 번호. 없거나 자리가 장소 사이가 아니면 None."""
    visit = plan.get('festival_visit')
    if not isinstance(visit, dict) or visit.get('position') != 'middle':
        return None
    after = visit.get('after')
    places = plan.get('places') or []
    if isinstance(after, int) and not isinstance(after, bool) and 0 <= after < len(places) - 1:
        return after
    return None


def endpoints(plan):
    """구간마다 (출발 id, 도착 id). 귀가 구간이 있으면 마지막이 (마지막 장소 id, 'home').
    코스 중간 축제 뒤 구간(행사장 → 다음 장소)은 ('festival', 다음 장소 id)."""
    ids = ['origin', *[p['id'] for p in plan['places']]]
    pairs = list(zip(ids, ids[1:]))
    after = middle_after(plan)
    if after is not None:
        pairs[after + 1] = ('festival', ids[after + 2])
    if len(plan.get('legs') or []) > len(plan['places']):
        pairs.append((ids[-1], 'home'))
    return pairs


def festival_pair(plan):
    """행사장으로 가는 축제 구간 키 (장소 id, 'festival'). 그 구간은 plan['legs'] 밖(festival_visit.leg)에 있다(app/festival_time.py).
    코스 끝 저녁 축제면 마지막 장소, 코스 중간 축제면 축제 바로 앞 장소에서 간다. 둘 다 아니면 None."""
    visit = plan.get('festival_visit')
    if isinstance(visit, dict) and visit.get('position') == 'last' and plan.get('places'):
        return plan['places'][-1]['id'], 'festival'
    after = middle_after(plan)
    if after is not None:
        return plan['places'][after]['id'], 'festival'
    return None


def festival_leg(plan):
    """돌아오는 구간(festival_visit.leg)에 경고 문장용 출발·도착 이름을 붙인 사본. 저녁 축제가 없으면 None.
    저장된 구간에는 장소 이름을 싣지 않으므로(app/festival_time.LEG_FIELDS) 이름은 코스에서 찾는다."""
    pair = festival_pair(plan)
    leg = (plan.get('festival_visit') or {}).get('leg')
    if not pair or not isinstance(leg, dict):
        return None
    names = place_names(plan)
    return dict(leg, origin=names.get(pair[0], ''), destination=names.get('festival', ''))


def leg_mode(plan, index):
    leg = plan['legs'][index]
    return leg.get('mode') or (plan.get('conditions') or {}).get('transport') or 'walk'


def next_leg_modes(plan, default=None, legs=(), festival=None):
    """요청을 적용한 뒤의 (기본 수단, leg_modes 목록).

    default가 있으면 기본 수단을 바꾸고 예외를 지운다. 기본 수단과 같은 수단으로 바꾼 구간은 예외에서 지운다.
    지금 코스에 없는 구간(장소를 바꿔 끊긴 예외)은 남기지 않는다. festival 은 저녁 축제로 돌아오는 구간의 수단(festival_pair)."""
    c = Conditions.model_validate(plan['conditions'])
    pairs = endpoints(plan)
    extra = festival_pair(plan)
    if extra:
        pairs = pairs + [extra]
    current = set(pairs)
    transport = default or c.transport
    overrides = {} if default else {(m.from_, m.to): m.mode for m in c.leg_modes if (m.from_, m.to) in current}
    for index, mode in legs:
        key = pairs[index]
        if mode == transport:
            overrides.pop(key, None)
        else:
            overrides[key] = mode
    if festival and extra:
        if festival == transport:
            overrides.pop(extra, None)
        else:
            overrides[extra] = festival
    ordered = [dict(zip(('from', 'to'), key), mode=overrides[key]) for key in pairs if key in overrides]
    return transport, ordered


def place_names(plan):
    c = plan.get('conditions') or {}
    names = {'origin': (c.get('origin') or {}).get('name') or '출발지',
             'home': (c.get('home') or {}).get('name') or '귀가지'}
    names.update({p['id']: p['name'] for p in plan['places']})
    visit = plan.get('festival_visit')
    if isinstance(visit, dict) and visit.get('title'):
        names['festival'] = visit['title'] + ' 행사장'
    return names


def car_position_notes(plan):
    """차는 출발지에 있다고 보고, 자동차 구간을 지나면 도착지로 옮긴다.

    자동차 구간의 출발지가 차가 있는 곳과 다르거나, 차를 둔 채 다른 수단으로 귀가하면 안내한다.
    돌아가는 시간·주차 시간·택시 요금은 만들지 않는다. 아무것도 막지 않는다."""
    legs = plan.get('legs') or []
    # (출발, 도착, 수단) 순서. 코스 끝 저녁 축제면 마지막 장소 → 행사장(festival_visit.leg) 뒤에 행사장에서 귀가한다.
    steps = [(start, end, leg_mode(plan, i)) for i, (start, end) in enumerate(endpoints(plan)[:len(legs)])]
    extra = festival_pair(plan)
    after = middle_after(plan)
    if extra:
        mode = plan['festival_visit'].get('leg', {}).get('mode') or (plan.get('conditions') or {}).get('transport') or 'walk'
        if after is not None:
            # 코스 중간 축제: 앞 장소 → 행사장 뒤에 행사장 → 다음 장소(endpoints 가 이미 ('festival', 다음 장소)).
            steps = steps[:after + 1] + [(extra[0], 'festival', mode)] + steps[after + 1:]
        else:
            home = steps[len(plan['places'])] if len(steps) > len(plan['places']) else None
            steps = steps[:len(plan['places'])] + [(extra[0], 'festival', mode)] + ([('festival', 'home', home[2])] if home else [])
    if not any(mode == 'car' for _, _, mode in steps):
        return []
    names = place_names(plan)
    # 행사장 = 출발지 좌표(app/festival_time.py). 차 위치를 비교할 때는 같은 곳으로 본다.
    same = lambda a, b: {a, b} <= {'origin', 'festival'} or a == b
    car_at, used, notes = 'origin', False, []
    for start, end, mode in steps:
        if mode == 'car':
            if not same(car_at, start):
                place = names.get(car_at, '출발지')
                target = names.get(end, '')
                notes.append(
                    f"차는 {place} 근처에 있어요. {names.get(start, '')} → {target}{josa(target, '을', '를')} 자동차로 가려면 "
                    '차가 있는 곳까지 돌아가야 하고, 그 시간은 계산에 없어요. 택시라면 요금이 비용에 빠져 있어요.')
            car_at, used = end, True
        elif end == 'home' and used and car_at != 'home':
            place = names.get(car_at, '출발지')
            notes.append(
                f"차는 {place} 근처에 있어요. 귀가를 {NAMES.get(mode, mode)}{josa(NAMES.get(mode, mode), '으로', '로')} 하면 "
                '차를 그곳에 두고 가게 돼요. 차를 가지러 가는 시간은 계산에 없어요.')
    return notes


def describe(before, after, changed, default=None, cleared=False, conditions=None, fallback=()):
    """바꾼 결과를 쉬운 말로. 값은 계산된 시간표에서만 가져온다."""
    from .planner import minutes
    c = conditions
    arrivals = []
    for b_place, b_time, a_time in zip(before['places'], before['timeline'], after['timeline']):
        shift = minutes(a_time['arrival']) - minutes(b_time['arrival'])
        arrivals.append(dict(place_id=b_place['id'], name=b_place['name'], before=b_time['arrival'],
                             after=a_time['arrival'], shift=shift))
    finish = dict(before=before['finish'], after=after['finish'])
    finish_text = f"종료는 {finish['before']} → {finish['after']}이에요." if finish['before'] != finish['after'] else f"종료는 {finish['after']} 그대로예요."
    messages = []
    if default:
        name = NAMES[default]
        messages.append(f"모든 구간을 {name}{josa(name, '으로', '로')} 바꿨어요." + (' 따로 고른 구간 설정은 지웠어요.' if cleared else '') + ' ' + finish_text)
    elif changed:
        first = changed[0]
        name = NAMES[first['after']]
        subject = '이 구간을' if len(changed) == 1 else f'고른 구간 {len(changed)}개를'
        later = [a for a in arrivals if a['place_id'] == first['to']]
        shift = later[0]['shift'] if later else minutes(finish['after']) - minutes(finish['before'])
        moved = f'이후 도착이 {abs(shift)}분 당겨지고' if shift < 0 else f'이후 도착이 {shift}분 늦어지고' if shift > 0 else '이후 도착 시간은 그대로이고'
        messages.append(f"{subject} {name}{josa(name, '으로', '로')} 바꿨어요. {moved} {finish_text}")
    warnings = []
    # 코스 끝 저녁 축제로 돌아오는 구간(festival_visit.leg)도 다른 구간과 같은 기준으로 경고한다.
    extra = festival_leg(after)
    if c is not None:
        late = minutes(after['finish']) - minutes(c.end)
        if late > 0:
            warnings.append(f'종료가 요청한 {c.end}보다 {late}분 늦어져요. 그대로 저장했어요.')
        for leg in after['legs'] + ([extra] if extra else []):
            if leg.get('minutes') is not None and leg['minutes'] > c.max_leg:
                warnings.append(f"{leg['origin']} → {leg['destination']} 이동이 {leg['minutes']}분으로 요청한 {c.max_leg}분보다 길어요. 그대로 저장했어요.")
        if c.max_walk is not None and (after.get('walking') or 0) > c.max_walk:
            warnings.append(f"총 도보가 {after['walking']}분으로 요청한 {c.max_walk}분보다 길어요. 그대로 저장했어요.")
    for index in fallback:
        leg = after['legs'][index]
        warnings.append(f"자동차 길찾기 조회에 실패해 이 구간은 추정 시간이에요. ({leg['origin']} → {leg['destination']})")
    if extra and extra.get('route_fallback'):
        warnings.append(f"자동차 길찾기 조회에 실패해 이 구간은 추정 시간이에요. ({extra['origin']} → {extra['destination']})")
    return dict(changed=changed, arrivals=arrivals, finish=finish, messages=messages, warnings=warnings,
                car_notes=car_position_notes(after))


class NoChange(ValueError):
    pass


class Blocked(ValueError):
    pass


def prepare_change(plan, default=None, legs=(), festival=None):
    """요청을 새 조건과 구간별 전후 수단으로 바꾼다. 아직 계산하지 않는다.
    festival: 코스 끝 저녁 축제로 돌아오는 구간의 새 수단. 이 구간은 plan['legs'] 밖이라 pairs 끝에 따로 붙인다."""
    pairs = endpoints(plan)
    if len(pairs) != len(plan.get('legs') or []):
        raise ValueError('이 코스의 구간 정보를 확인하지 못했어요. 코스를 다시 열어 주세요.')
    if any(not 0 <= index < len(pairs) for index, _ in legs):
        raise ValueError('없는 구간이에요. 코스를 다시 열어 주세요.')
    extra = festival_pair(plan)
    if festival and not extra:
        raise ValueError('코스 끝이나 중간에 둔 축제가 없는 코스예요. 코스를 다시 열어 주세요.')
    c = Conditions.model_validate(plan['conditions'])
    transport, modes = next_leg_modes(plan, default, legs, festival)
    conditions = Conditions.model_validate(dict(plan['conditions'], transport=transport, leg_modes=modes))
    overrides = {(m['from'], m['to']): m['mode'] for m in modes}
    before = [leg_mode(plan, i) for i in range(len(pairs))]
    after = [overrides.get(key, transport) for key in pairs]
    if extra:
        pairs = pairs + [extra]
        before.append(plan['festival_visit'].get('leg', {}).get('mode') or c.transport)
        after.append(overrides.get(extra, transport))
    if before == after and transport == c.transport and len(modes) == len(c.leg_modes):
        raise NoChange('이미 그 이동 수단이에요.')
    return dict(conditions=conditions, pairs=pairs, before=before, after=after, default=default,
                cleared=bool(default and c.leg_modes))


def apply_change(plan, prepared):
    """새 수단으로 시간표를 다시 계산한다. 영업시간·휴무·마지막 입장을 어기면 Blocked.
    종료 시각·구간 이동·총 도보 초과는 경고로 남긴다(필수 조건이면 저장 단계의 hard_blocks가 막는다)."""
    import copy
    from contextlib import nullcontext
    from .planner import evaluate
    from .request_usage import measure
    c = prepared['conditions']
    car_legs = sum(mode == 'car' for mode in prepared['after'])
    verify = c.mode == 'real' and car_legs > 0
    failure = {}
    # 실제 길찾기는 자동차 구간에만, 캐시를 먼저 보고, 이번 변경에서 자동차 구간 수(최대 6)까지만 부른다.
    # 코스 중간 축제는 같은 자리(앞 장소 번호)에만 두고 다시 계산한다. 그 자리에 못 두면 evaluate 가 실패한다(아래 blocked_message).
    after = middle_after(plan)
    # 지각 복구로 저장한 코스(plan['delay_recovery'])는 그때 반영한 지연을 다시 넣어 계산한다. 넣지 않으면 수단만 바꿨는데
    # 시간표가 '늦지 않은 것'으로 돌아가 틀린 시각을 믿게 된다. 지연은 '그 장소에 원래보다 N분 늦게 닿음'이라 수단과 무관하게 유효하다.
    # 기록 자체는 저장할 때 이어 붙인다(app/main.py transport → plan_changes.save_change(recovery=…)). 장소를 바꾸는 변경은 이어받지 않는다.
    from .delay_check import carried_delays
    delays = carried_delays(plan)
    with measure(limit=min(MAX_ROUTE_CALLS, car_legs)) if verify else nullcontext():
        checked, error = evaluate(plan['places'], c, soft=True, verify_routes=verify, route_fallback=True, failure=failure,
                                  festival_after=after, delays=delays or None)
    if error:
        raise Blocked(blocked_message(failure))
    # 코스 끝 저녁 축제가 새 수단으로는 운영 시간에 맞지 않으면(개막까지 너무 오래 기다리거나 종료를 넘김) planner 는 축제 없이 끝내거나
    # 코스 중간으로 옮긴다. 그대로 저장하면 축제가 말없이 빠지거나 자리가 바뀌므로 바꾸지 않는다.
    visit = checked.get('festival_visit') or {}
    if festival_pair(plan) and after is None and visit.get('position') != 'last':
        raise Blocked('이 수단으로는 코스 끝 축제 시간에 맞출 수 없어 바꾸지 않았어요. 축제 개막까지 너무 오래 기다리거나 운영 시간을 넘겨요.')
    if after is not None and (visit.get('position') != 'middle' or visit.get('after') != after):
        raise Blocked(MIDDLE_BLOCKED)
    updated = copy.deepcopy(plan)
    # 축제 방문 기록은 다시 계산한 코스를 따른다(남은 옛 기록이 화면·지도·지각 확인에 쓰이지 않게).
    updated.pop('festival_visit', None)
    reasons = updated.get('reasons')
    updated.update(checked)
    if reasons:
        updated['reasons'] = reasons  # 장소별 추천 이유는 수단과 무관하다(블로그 순위 등 유지).
    if plan.get('best_effort'):
        from .best_effort import annotate
        updated = annotate(updated, c)
    fallback = [i for i, leg in enumerate(updated['legs']) if leg.get('route_fallback')]
    festival_fallback = bool(((updated.get('festival_visit') or {}).get('leg') or {}).get('route_fallback'))
    if verify:
        updated['route_verification'] = (
            '바꾼 자동차 구간의 실제 경로를 다시 확인했어요. 조회 시점 기준입니다.' if not fallback and not festival_fallback
            else '자동차 길찾기 조회에 실패한 구간은 추정 시간이에요.')
    else:
        updated.pop('route_verification', None)
    updated['delta'] = dict(minutes=updated['minutes'] - plan['minutes'],
                            cost=[updated['total'][i] - plan['total'][i] for i in (0, 1)],
                            total_before=list(plan['total']))
    updated['change_reason'] = '이동 수단을 바꿔 이동·시간·비용을 다시 계산했어요.'
    if delays:
        # 가장 큰 지연 하나만 적는다(기록은 보통 한 장소뿐이고, 여러 번 복구하면 같은 장소에 더해진다).
        updated['change_reason'] += f' 앞서 반영한 {max(delays.values())}분 지연은 그대로 뒀어요.'
    # 수단을 바꿔 축제가 새로 들어갔으면(예: 빨라져 운영 시간에 맞음) 말없이 넣지 않고 알린다. 빠지거나 옮겨지는 변경은 위에서 이미 거절했다.
    from .festival_time import set_change_note
    set_change_note(updated, plan)
    names = place_names(plan)
    changed = [dict(index=i, **{'from': start}, to=end, origin=names.get(start, ''), destination=names.get(end, ''),
                    before=prepared['before'][i], after=prepared['after'][i])
               for i, (start, end) in enumerate(prepared['pairs']) if prepared['before'][i] != prepared['after'][i]]
    summary = describe(plan, updated, changed, default=prepared['default'], cleared=prepared['cleared'],
                       conditions=c, fallback=fallback)
    return updated, summary


MIDDLE_BLOCKED = '이 수단으로는 코스 중간 축제 시간에 맞출 수 없어 바꾸지 않았어요. 축제 개막까지 너무 오래 기다리거나 운영 시간을 넘겨요.'


def blocked_message(failure, mode=None):
    """바꾸지 못한 이유. evaluate()가 채운 failure(장소·제한 시각)만 쓴다."""
    from .planner import MIDDLE_MISS
    name = failure.get('place') or '방문 장소'
    lead = f"이 수단으로는 {name}" if mode is None else f"{NAMES.get(mode, '이 수단')}{josa(NAMES.get(mode, ''), '으로', '로')}는 {name}"
    reason = failure.get('reason')
    if reason == MIDDLE_MISS:
        return MIDDLE_BLOCKED
    if reason == '마지막 입장 시간 초과':
        return f"{lead} 마지막 입장({failure.get('limit')}) 전에 도착하지 못해 바꾸지 않았어요."
    if reason == '영업시간 밖 방문':
        return f"{lead} 영업 종료({failure.get('limit')}) 전에 방문을 마치지 못해 바꾸지 않았어요."
    if reason == '방문일 휴무':
        return f"{name}{josa(name, '은', '는')} 방문일에 쉬는 날이라 바꾸지 않았어요."
    return f"이 수단으로는 일정을 맞추지 못해 바꾸지 않았어요. ({reason or '확인 필요'})"
