"""Engine chấm điểm KPI - hàm thuần, không phụ thuộc ORM để dễ kiểm thử.

Engine không tự suy diễn: thiếu dữ liệu/thiếu điều kiện -> trả score=None kèm ghi chú.
Mọi tham số (điểm trần, sàn, mức trừ, bước ngày...) đến từ cấu hình rule/dòng KPI.
"""
import math

OPS = {
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b,
    '=': lambda a, b: a == b,
    '>': lambda a, b: a > b,
    '<': lambda a, b: a < b,
}


def _clamp(score, cap, floor):
    if score is None:
        return None
    if cap is not None:
        score = min(score, cap)
    if floor is not None:
        score = max(score, floor)
    return score


def compute_score(cfg, target_op, target, actual, actual_entered, delay_days, events,
                  objective_exception=False, score_cap=None):
    """Trả về dict(score, rate, note).

    cfg: {'method', 'score_cap', 'score_floor', 'combine_mode', 'exception_deduct_pct',
          'lines': [{'sequence','op','threshold','level','action','value','step'}]}
    events: danh sách mức độ (light/medium/heavy/critical) của sự việc đã xác nhận, có ảnh hưởng điểm.
    delay_days: số ngày chậm (>0 là chậm) hoặc None nếu chưa có ngày hoàn thành thực tế.
    """
    method = cfg.get('method')
    cap = score_cap if score_cap else cfg.get('score_cap', 100)
    floor = cfg.get('score_floor', 0)
    lines = sorted(cfg.get('lines') or [], key=lambda l: l.get('sequence', 0))
    res = {'score': None, 'rate': None, 'note': ''}

    if method == 'MANUAL':
        res['note'] = 'Nhập điểm thủ công có thẩm định'
        return res

    event_based = method in ('INCIDENT_COUNT', 'LEVEL')
    if not actual_entered and not event_based and method != 'DATE_DELAY':
        res['note'] = 'Chưa có dữ liệu tại mốc chốt'
        return res

    score = None
    if method == 'RATE':
        if not target:
            res['note'] = 'Chỉ tiêu = 0: cần dùng quy tắc điều kiện/sự kiện'
            return res
        rate = actual / target * 100.0
        res['rate'] = rate
        score = rate
    elif method == 'REVERSE_RATE':
        if actual <= 0:
            score = cap
            res['rate'] = 100.0
        elif not target:
            res['note'] = 'Chỉ tiêu = 0: cần dùng quy tắc điều kiện/sự kiện'
            return res
        else:
            res['rate'] = target / actual * 100.0
            score = res['rate']
    elif method == 'THRESHOLD':
        for l in lines:
            op = OPS.get(l.get('op') or '>=')
            if op(actual, l.get('threshold') or 0.0):
                score = l.get('value') or 0.0
                res['note'] = l.get('label') or ''
                break
        if score is None:
            res['note'] = 'Không có điều kiện ngưỡng nào thỏa mãn'
            return res
        res['rate'] = score
    elif method == 'DATE_DELAY':
        if delay_days is None:
            res['note'] = 'Chưa có ngày hoàn thành thực tế'
            return res
        if delay_days <= 0:
            score = 100.0
        else:
            first = lines[0] if lines else {}
            step = first.get('step') or 1.0
            deduct = math.floor(delay_days / step) * (first.get('value') or 0.0)
            score = 100.0 - deduct
            res['note'] = 'Chậm %s ngày' % delay_days
        res['rate'] = score
    elif method == 'INCIDENT_COUNT':
        count = len(events) if events else int(actual or 0)
        if any(l.get('action') == 'zero' and l.get('level') in events for l in lines) or \
                ('critical' in events and any(l.get('action') == 'zero' for l in lines)):
            score = 0.0
            res['note'] = 'Sự việc nghiêm trọng: 0 điểm'
        else:
            per = 0.0
            for l in lines:
                if l.get('action') == 'deduct_pct':
                    per = l.get('value') or 0.0
                    break
            score = 100.0 - count * per
            res['note'] = '%s sự việc/lỗi' % count
        res['rate'] = score
    elif method == 'LEVEL':
        deds = []
        for sev in events:
            for l in lines:
                if l.get('level') == sev:
                    if l.get('action') == 'factor':
                        deds.append(100.0 - (l.get('value') or 0.0) * 100.0)
                    else:
                        deds.append(l.get('value') or 0.0)
                    break
        mode = cfg.get('combine_mode') or 'sum'
        if not deds:
            score = 100.0
        elif mode == 'max':
            score = 100.0 - max(deds)
        elif mode == 'multiply':
            score = 100.0
            for d in deds:
                score *= (1 - d / 100.0)
        else:
            score = 100.0 - sum(deds)
        res['rate'] = score
    elif method == 'BINARY':
        ok = bool(actual)
        score = 100.0 if ok else 0.0
        res['rate'] = score
    else:
        res['note'] = 'Phương pháp chưa hỗ trợ: %s' % method
        return res

    if objective_exception and cfg.get('exception_deduct_pct'):
        score -= cfg['exception_deduct_pct']
        res['note'] = (res['note'] + '; ' if res['note'] else '') + \
            'Ngoại lệ khách quan -%s%%' % cfg['exception_deduct_pct']
    res['score'] = _clamp(score, cap, floor)
    return res


def aggregate(scores, method, primary_score=None):
    """Tổng hợp nhiều reviewer: average / primary. Không mặc định trung bình."""
    scores = [s for s in scores if s is not None]
    if method == 'primary':
        return primary_score
    if method == 'average':
        return sum(scores) / len(scores) if scores else None
    return None
