"""
Casino Routes — Flask routes for 19 casino games, admin panel, and API endpoints
"""
from flask import request, jsonify, session, render_template_string, redirect, Response
from functools import wraps
from modules.casino import (
    GAMES, GAME_META,
    play_head_tail, play_rock_paper_scissors, play_spin_wheel,
    play_number_guess, play_dice_rolling, play_card_finding,
    play_number_slot, play_number_pool, play_roulette,
    play_casino_dice, play_keno, play_blackjack_deal, play_blackjack_action,
    play_mines_start, play_mines_reveal, play_mines_cashout,
    play_poker_deal, play_poker_draw,
    play_color_prediction, play_crazy_times, play_dream_catcher,
    play_andar_bahar, play_pai_gow_poker,
    play_crash_start, play_crash_cashout, play_crash_status,
    get_casino_stats, get_user_casino_stats, get_recent_bets,
    claim_daily_free, can_claim_daily, get_free_balance,
    get_next_claim_time, get_daily_free_winnings,
    get_house_edge, set_house_edge, is_game_enabled, set_game_enabled,
    is_casino_enabled, is_daily_free_enabled, get_daily_free_amount,
    get_daily_free_max_win, get_min_bet, get_max_bet,
    set_setting, get_setting, DEFAULT_HOUSE_EDGES, cleanup_sessions,
    get_leaderboard, get_user_achievements, ACHIEVEMENT_DEFS,
    get_achievement_stats, revoke_achievement, grant_achievement,
    get_lb_reward_config, set_lb_reward_setting, process_leaderboard_rewards,
    get_reward_history,
    get_username, search_users, get_username_map,
    get_achievement_unlock_timeline, get_all_bets_for_export,
)
from modules.cc_shop import get_user_balance, add_user_balance
import json
import csv
import io


GAME_CATEGORIES = {
    'quick': {'name': 'Quick Games', 'games': ['head_tail', 'rock_paper_scissors', 'color_prediction', 'number_pool']},
    'wheel': {'name': 'Wheel & Spin', 'games': ['spin_wheel', 'dream_catcher', 'crazy_times']},
    'dice': {'name': 'Dice & Numbers', 'games': ['dice_rolling', 'casino_dice', 'number_guess', 'number_slot']},
    'cards': {'name': 'Card Games', 'games': ['blackjack', 'poker', 'andar_bahar', 'pai_gow_poker', 'card_finding']},
    'special': {'name': 'Special', 'games': ['crash', 'roulette', 'keno', 'mines']},
}


def register_casino_routes(app, user_required, owner_required, get_user_sidebar, USER_CSS, ADMIN_CSS):

    @app.route('/user/casino')
    @user_required
    def user_casino():
        user_id = session.get('user_id')
        balance = get_user_balance(user_id)
        free_bal = get_free_balance(user_id)
        can_claim = can_claim_daily(user_id)
        next_claim = get_next_claim_time()
        daily_amount = get_daily_free_amount()
        daily_enabled = is_daily_free_enabled()
        user_stats = get_user_casino_stats(user_id)
        casino_on = is_casino_enabled()
        min_bet = get_min_bet()
        max_bet = get_max_bet()

        games_data = []
        games_html_cards = ''
        for g in GAMES:
            enabled = is_game_enabled(g)
            edge = get_house_edge(g)
            meta = GAME_META.get(g, {})
            games_data.append({'id': g, 'enabled': enabled, 'edge': edge})
            icon = meta.get('icon', '🎮')
            name = meta.get('name', g.replace('_', ' ').title())
            win_pct = meta.get('win', 100 - edge)
            disabled_cls = '' if enabled else ' disabled'
            games_html_cards += f'''<div class="game-card thumb-{g}{disabled_cls}" onclick="openGame('{g}')">
                <div class="thumb" data-name="{name}"><div class="thumb-icon">{icon}</div><div class="thumb-shine"></div></div>
                <div class="card-body"><div class="name">{name}</div><div class="edge">{win_pct}% RTP</div></div>
            </div>'''

        cat_tabs = ''
        cat_idx = 0
        for cid, cinfo in GAME_CATEGORIES.items():
            active = ' active' if cat_idx == 0 else ''
            cat_tabs += f'<button class="cat-tab{active}" onclick="switchTab(\'{cid}\')">{cinfo["name"]}</button>'
            cat_idx += 1
        cat_tabs += '<button class="cat-tab" onclick="switchTab(\'all\')">All Games</button>'

        return render_template_string(CASINO_PAGE_HTML,
            sidebar=get_user_sidebar('casino', 'Casino'),
            user_css=USER_CSS,
            balance=f"{balance:.2f}",
            free_balance=f"{free_bal:.2f}",
            can_claim='true' if can_claim else 'false',
            next_claim=next_claim,
            daily_amount=f"{daily_amount:.2f}",
            daily_enabled='true' if daily_enabled else 'false',
            casino_enabled='true' if casino_on else 'false',
            min_bet=f"{min_bet:.2f}",
            max_bet=f"{max_bet:.2f}",
            total_bets=user_stats['bets'],
            total_wagered=f"{user_stats['wagered']:.2f}",
            games_html_cards=games_html_cards,
            total_won=f"{user_stats['won']:.2f}",
            net=f"{user_stats['net']:.2f}",
            games_json=json.dumps(games_data),
            cat_tabs=cat_tabs,
            categories_json=json.dumps({k: v['games'] for k, v in GAME_CATEGORIES.items()}),
        )

    @app.route('/api/casino/play', methods=['POST'])
    @user_required
    def api_casino_play():
        user_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
        game = data.get('game', '')
        is_free = bool(data.get('free_play', False))
        result = _dispatch_game(user_id, game, data, is_free)
        if 'error' not in result:
            result['balance'] = f"{get_user_balance(user_id):.2f}"
            result['free_balance'] = f"{get_free_balance(user_id):.2f}"
        return jsonify(result)

    def _dispatch_game(user_id, game, data, is_free):
        bet_val = data.get('bet', 0)
        try:
            bet = round(float(bet_val), 2)
        except (ValueError, TypeError):
            return {'error': 'Invalid bet amount'}
        is_continuation = bool(data.get('session_id')) and bool(data.get('action'))
        if bet <= 0 and not is_continuation:
            return {'error': 'Bet must be positive'}

        if game == 'head_tail':
            return play_head_tail(user_id, bet, data.get('choose', 'head'), is_free)
        elif game == 'rock_paper_scissors':
            return play_rock_paper_scissors(user_id, bet, data.get('choose', 'rock'), is_free)
        elif game == 'spin_wheel':
            return play_spin_wheel(user_id, bet, is_free)
        elif game == 'number_guess':
            return play_number_guess(user_id, bet, data.get('guess_number'), is_free)
        elif game == 'dice_rolling':
            return play_dice_rolling(user_id, bet, data.get('choose', 'high'), is_free)
        elif game == 'card_finding':
            return play_card_finding(user_id, bet, data.get('position', 0), is_free)
        elif game == 'number_slot':
            return play_number_slot(user_id, bet, is_free)
        elif game == 'number_pool':
            return play_number_pool(user_id, bet, data.get('choose', 'odd'), is_free)
        elif game == 'roulette':
            return play_roulette(user_id, bet, data.get('bet_type', 'red'), data.get('bet_value'), is_free)
        elif game == 'casino_dice':
            return play_casino_dice(user_id, bet, data.get('percent', 50), data.get('choose', 'low'), is_free)
        elif game == 'keno':
            return play_keno(user_id, bet, data.get('picks', []), is_free)
        elif game == 'blackjack':
            action = data.get('action', 'deal')
            sid = data.get('session_id', '')
            if action == 'deal':
                return play_blackjack_deal(user_id, bet, is_free)
            else:
                return play_blackjack_action(user_id, sid, action)
        elif game == 'mines':
            action = data.get('action', 'start')
            sid = data.get('session_id', '')
            if action == 'start':
                return play_mines_start(user_id, bet, data.get('num_mines', 3), is_free)
            elif action == 'reveal':
                return play_mines_reveal(user_id, sid, data.get('position', 0))
            elif action == 'cashout':
                return play_mines_cashout(user_id, sid)
            else:
                return {'error': 'Invalid mines action'}
        elif game == 'poker':
            action = data.get('action', 'deal')
            sid = data.get('session_id', '')
            if action == 'deal':
                return play_poker_deal(user_id, bet, is_free)
            else:
                return play_poker_draw(user_id, sid, data.get('hold', []))
        elif game == 'color_prediction':
            return play_color_prediction(user_id, bet, data.get('choose', 'red'), is_free)
        elif game == 'crazy_times':
            return play_crazy_times(user_id, bet, data.get('choose', '1'), is_free)
        elif game == 'dream_catcher':
            return play_dream_catcher(user_id, bet, data.get('choose', '1'), is_free)
        elif game == 'andar_bahar':
            return play_andar_bahar(user_id, bet, data.get('choose', 'andar'), is_free)
        elif game == 'pai_gow_poker':
            return play_pai_gow_poker(user_id, bet, is_free)
        elif game == 'crash':
            action = data.get('action', 'start')
            sid = data.get('session_id', '')
            if action == 'start':
                return play_crash_start(user_id, bet, is_free, data.get('auto_cashout'))
            elif action == 'cashout':
                return play_crash_cashout(user_id, sid)
            elif action == 'status':
                return play_crash_status(user_id, sid)
            else:
                return {'error': 'Invalid crash action'}
        else:
            return {'error': 'Unknown game'}

    @app.route('/api/casino/play/<game_name>', methods=['POST'])
    @user_required
    def api_casino_play_game(game_name):
        user_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
        is_free = bool(data.get('free_play', False))
        result = _dispatch_game(user_id, game_name, data, is_free)
        if 'error' not in result:
            result['balance'] = f"{get_user_balance(user_id):.2f}"
            result['free_balance'] = f"{get_free_balance(user_id):.2f}"
        return jsonify(result)

    @app.route('/api/casino/bet', methods=['POST'])
    @user_required
    def api_casino_bet():
        return api_casino_play()

    @app.route('/api/casino/daily-claim', methods=['POST'])
    @user_required
    def api_casino_daily_claim():
        user_id = session.get('user_id')
        result = claim_daily_free(user_id)
        if 'error' not in result:
            result['free_balance'] = f"{get_free_balance(user_id):.2f}"
            result['balance'] = f"{get_user_balance(user_id):.2f}"
        return jsonify(result)

    @app.route('/api/casino/balance')
    @user_required
    def api_casino_balance():
        user_id = session.get('user_id')
        return jsonify({
            'balance': f"{get_user_balance(user_id):.2f}",
            'free_balance': f"{get_free_balance(user_id):.2f}",
            'can_claim': can_claim_daily(user_id),
            'next_claim': get_next_claim_time(),
        })

    @app.route('/api/casino/history')
    @user_required
    def api_casino_history():
        user_id = session.get('user_id')
        bets = get_recent_bets(50, user_id)
        result = []
        for b in bets:
            result.append({
                'game': b['game'],
                'bet': float(b['bet_amount']),
                'win': float(b['win_amount']),
                'result': b['result'],
                'free': b['is_free_play'],
                'time': b['created_at'].strftime('%Y-%m-%d %H:%M') if b.get('created_at') else '',
                'seed_hash': b.get('seed_hash', ''),
                'server_seed': b.get('server_seed', ''),
            })
        return jsonify(result)

    @app.route('/api/casino/stats')
    @user_required
    def api_casino_user_stats():
        user_id = session.get('user_id')
        stats = get_user_casino_stats(user_id)
        return jsonify(stats)

    @app.route('/api/casino/leaderboard')
    @user_required
    def api_casino_leaderboard():
        period = request.args.get('period', 'all')
        if period not in ('weekly', 'monthly', 'all'):
            period = 'all'
        data = get_leaderboard(period)
        lb_config = get_lb_reward_config()
        rewards_info = None
        if lb_config['enabled'] and period in ('weekly', 'monthly'):
            rewards_info = {str(k): v for k, v in lb_config[period].items()}
        return jsonify({'leaderboard': data, 'rewards': rewards_info})

    @app.route('/api/casino/achievements')
    @user_required
    def api_casino_achievements():
        user_id = session.get('user_id')
        unlocked = get_user_achievements(user_id)
        unlocked_ids = {a['id'] for a in unlocked}
        all_achievements = []
        for aid, defn in ACHIEVEMENT_DEFS.items():
            entry = {
                'id': aid, 'name': defn['name'], 'icon': defn['icon'],
                'description': defn['description'], 'unlocked': aid in unlocked_ids,
            }
            match = next((a for a in unlocked if a['id'] == aid), None)
            if match:
                entry['unlocked_at'] = match['unlocked_at']
            all_achievements.append(entry)
        return jsonify(all_achievements)

    @app.route('/admin/casino/export/achievements')
    @owner_required
    def export_achievements_csv():
        stats = get_achievement_stats()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Achievement ID', 'Name', 'Icon', 'Description', 'Total Unlocks'])
        for a in stats:
            writer.writerow([a['id'], a['name'], a['icon'], a['description'], a['unlock_count']])
        return Response(output.getvalue(), mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=achievement_stats.csv'})

    @app.route('/admin/casino/export/bets')
    @owner_required
    def export_bets_csv():
        bets = get_all_bets_for_export()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'User ID', 'Game', 'Bet Amount', 'Win Amount', 'Profit', 'Result', 'Free Play', 'Created At'])
        for b in bets:
            writer.writerow([b.get('id',''), b.get('user_id',''), b.get('game',''),
                f"{float(b.get('bet_amount',0)):.2f}", f"{float(b.get('win_amount',0)):.2f}",
                f"{float(b.get('profit',0)):.2f}", b.get('result',''),
                'Yes' if b.get('is_free_play') else 'No',
                b['created_at'].strftime('%Y-%m-%d %H:%M:%S') if b.get('created_at') else ''])
        return Response(output.getvalue(), mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=bet_history.csv'})

    @app.route('/admin/casino/export/achievement-timeline')
    @owner_required
    def export_achievement_timeline():
        return jsonify(get_achievement_unlock_timeline())

    @app.route('/admin/casino', methods=['GET', 'POST'])
    @owner_required
    def admin_casino():
        message = ""
        if request.method == 'POST':
            action = request.form.get('action', '')
            if action == 'save_edges':
                for g in GAMES:
                    val = request.form.get(f'edge_{g}')
                    if val:
                        try:
                            set_house_edge(g, float(val))
                        except (ValueError, TypeError):
                            pass
                message = "Win probabilities saved!"
            elif action == 'toggle_game':
                game = request.form.get('game', '')
                if game in GAMES:
                    current = is_game_enabled(game)
                    set_game_enabled(game, not current)
                    gname = GAME_META.get(game, {}).get('name', game.title())
                    message = f"{gname} {'disabled' if current else 'enabled'}!"
            elif action == 'toggle_casino':
                current = is_casino_enabled()
                set_setting('enabled', 'false' if current else 'true')
                message = f"Casino {'disabled' if current else 'enabled'}!"
            elif action == 'save_daily':
                try:
                    amt = float(request.form.get('daily_amount', 5))
                    max_win = float(request.form.get('daily_max_win', 20))
                    set_setting('daily_free_amount', str(amt))
                    set_setting('daily_free_max_win', str(max_win))
                    message = "Daily free play settings saved!"
                except (ValueError, TypeError):
                    message = "Invalid values!"
            elif action == 'toggle_daily':
                current = is_daily_free_enabled()
                set_setting('daily_free_enabled', 'false' if current else 'true')
                message = f"Daily free play {'disabled' if current else 'enabled'}!"
            elif action == 'save_limits':
                try:
                    mn = float(request.form.get('min_bet', 0.10))
                    mx = float(request.form.get('max_bet', 100))
                    set_setting('min_bet', str(mn))
                    set_setting('max_bet', str(mx))
                    message = "Bet limits saved!"
                except (ValueError, TypeError):
                    message = "Invalid values!"
            elif action == 'grant_achievement':
                try:
                    uid = int(request.form.get('user_id', 0))
                    aid = request.form.get('achievement_id', '')
                    if uid and aid:
                        uname = get_username(uid)
                        user_label = f"{uname} ({uid})" if uname else str(uid)
                        if grant_achievement(uid, aid):
                            message = f"Granted '{ACHIEVEMENT_DEFS[aid]['name']}' to {user_label}!"
                        else:
                            message = f"{user_label} already has that achievement."
                    else:
                        message = "Invalid user ID or achievement."
                except (ValueError, TypeError):
                    message = "Invalid user ID!"
            elif action == 'revoke_achievement':
                try:
                    uid = int(request.form.get('user_id', 0))
                    aid = request.form.get('achievement_id', '')
                    if uid and aid:
                        uname = get_username(uid)
                        user_label = f"{uname} ({uid})" if uname else str(uid)
                        if revoke_achievement(uid, aid):
                            message = f"Revoked '{ACHIEVEMENT_DEFS.get(aid, {}).get('name', aid)}' from {user_label}!"
                        else:
                            message = f"{user_label} does not have that achievement."
                    else:
                        message = "Invalid user ID or achievement."
                except (ValueError, TypeError):
                    message = "Invalid user ID!"
            elif action == 'toggle_lb_rewards':
                current = get_lb_reward_config()['enabled']
                set_lb_reward_setting('lb_rewards_enabled', not current)
                message = f"Leaderboard rewards {'disabled' if current else 'enabled'}!"
            elif action == 'toggle_auto_payout':
                current = get_lb_reward_config()['auto_payout']
                set_lb_reward_setting('lb_auto_payout', not current)
                message = f"Auto payout {'disabled' if current else 'enabled'}!"
            elif action == 'save_lb_rewards':
                try:
                    set_lb_reward_setting('lb_weekly_1st', float(request.form.get('weekly_1st', 50)))
                    set_lb_reward_setting('lb_weekly_2nd', float(request.form.get('weekly_2nd', 25)))
                    set_lb_reward_setting('lb_weekly_3rd', float(request.form.get('weekly_3rd', 10)))
                    set_lb_reward_setting('lb_monthly_1st', float(request.form.get('monthly_1st', 200)))
                    set_lb_reward_setting('lb_monthly_2nd', float(request.form.get('monthly_2nd', 100)))
                    set_lb_reward_setting('lb_monthly_3rd', float(request.form.get('monthly_3rd', 50)))
                    message = "Leaderboard reward amounts saved!"
                except (ValueError, TypeError):
                    message = "Invalid reward values!"
            elif action == 'load_funds':
                try:
                    uid = int(request.form.get('fund_user_id', 0))
                    amt = float(request.form.get('fund_amount', 0))
                    note = request.form.get('fund_note', '').strip() or 'Admin credit'
                    if uid and amt != 0:
                        add_user_balance(uid, amt)
                        uname = get_username(uid)
                        ulabel = f"@{uname} ({uid})" if uname else str(uid)
                        sign = '+' if amt > 0 else ''
                        message = f"Funds {sign}${amt:.2f} loaded to {ulabel}. Note: {note}"
                    else:
                        message = "Invalid user ID or amount."
                except (ValueError, TypeError):
                    message = "Invalid fund-load values!"
            elif action == 'payout_rewards':
                period = request.form.get('payout_period', '')
                if period in ('weekly', 'monthly'):
                    result = process_leaderboard_rewards(period)
                    if result.get('error'):
                        message = f"Payout error: {result['error']}"
                    else:
                        payouts = result.get('payouts', [])
                        if payouts:
                            payout_summary = ', '.join([f"#{p['rank']} {p['username']}: ${p['reward']:.2f}" for p in payouts])
                            message = f"{period.title()} rewards paid! {payout_summary}"
                        else:
                            message = "No eligible players for payout."
                else:
                    message = "Invalid payout period!"

        lookup_user_id = request.args.get('lookup_user', '') or request.form.get('lookup_user_preserve', '')
        lookup_achievements = []
        lookup_username = ''
        if lookup_user_id:
            try:
                lookup_achievements = get_user_achievements(int(lookup_user_id))
                lookup_username = get_username(int(lookup_user_id)) or ''
            except (ValueError, TypeError):
                lookup_user_id = ''

        stats = get_casino_stats()
        recent = get_recent_bets(30)

        games_html = ""
        for g in GAMES:
            edge = get_house_edge(g)
            enabled = is_game_enabled(g)
            meta = GAME_META.get(g, {})
            gname = meta.get('name', g.replace('_', ' ').title())
            gicon = meta.get('icon', '🎮')
            win_pct = 100 - edge
            status_class = 'color:#4ade80' if enabled else 'color:#ef4444'
            games_html += f"""
            <tr>
                <td style="font-weight:600">{gicon} {gname}</td>
                <td><input type="number" name="edge_{g}" value="{edge}" step="0.1" min="0" max="50"
                    style="width:80px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);
                    color:#fff;padding:6px 10px;border-radius:6px;"></td>
                <td style="font-weight:600;color:#f1c40f">{win_pct:.1f}%</td>
                <td style="{status_class};font-weight:600">{'ON' if enabled else 'OFF'}</td>
                <td>
                    <form method="POST" style="display:inline">
                        <input type="hidden" name="action" value="toggle_game">
                        <input type="hidden" name="game" value="{g}">
                        <button type="submit" style="padding:4px 12px;border-radius:6px;border:none;cursor:pointer;
                            font-size:0.8em;background:{'#ef4444' if enabled else '#4ade80'};color:#fff">
                            {'Disable' if enabled else 'Enable'}</button>
                    </form>
                </td>
            </tr>"""

        casino_on = is_casino_enabled()
        daily_enabled = is_daily_free_enabled()
        daily_amount = get_daily_free_amount()
        daily_max = get_daily_free_max_win()
        min_bet = get_min_bet()
        max_bet = get_max_bet()
        lb_config = get_lb_reward_config()
        reward_hist = get_reward_history(20)
        ach_stats = get_achievement_stats()
        username_map = get_username_map([b['user_id'] for b in recent]) if recent else {}

        recent_html = ""
        for b in recent:
            uid = b['user_id']
            uname = username_map.get(str(uid))
            user_label = f"@{uname}" if uname else str(uid)
            gname = GAME_META.get(b['game'], {}).get('name', b['game'])
            r_color = '#4ade80' if b['result'] in ('win','blackjack') else ('#f1c40f' if b['result'] == 'push' else '#ef4444')
            recent_html += f"""<tr>
                <td>{user_label}</td><td>{gname}</td>
                <td>${float(b['bet_amount']):.2f}</td>
                <td style="color:{r_color}">${float(b['win_amount']):.2f}</td>
                <td style="color:{r_color}">{b['result'].upper()}</td>
                <td>{'Free' if b['is_free_play'] else 'Real'}</td>
                <td>{b['created_at'].strftime('%m/%d %H:%M') if b.get('created_at') else ''}</td></tr>"""

        ach_html = ""
        for a in ach_stats:
            ach_html += f"""<tr><td>{a['icon']} {a['name']}</td><td>{a['unlock_count']}</td>
                <td style="font-size:0.8em;color:#aaa">{a['description']}</td></tr>"""

        lookup_html = ""
        if lookup_user_id:
            user_label = f"@{lookup_username} ({lookup_user_id})" if lookup_username else str(lookup_user_id)
            lookup_html = f"<h4>Achievements for {user_label}:</h4>"
            if lookup_achievements:
                for la in lookup_achievements:
                    lookup_html += f"<div style='display:inline-block;background:rgba(255,255,255,0.1);padding:6px 12px;border-radius:8px;margin:4px'>{la['icon']} {la['name']} <small>({la['unlocked_at']})</small></div>"
            else:
                lookup_html += "<p style='color:#aaa'>No achievements yet.</p>"

        reward_html = ""
        for rh in reward_hist:
            reward_html += f"""<tr><td>#{rh['rank']}</td><td>{rh['username']}</td>
                <td>{rh['period'].title()}</td><td>${rh['reward_amount']:.2f}</td>
                <td>{rh['paid_at']}</td></tr>"""

        return render_template_string(ADMIN_CASINO_HTML,
            admin_css=ADMIN_CSS, message=message, stats=stats,
            games_html=games_html, casino_on=casino_on,
            daily_enabled=daily_enabled, daily_amount=daily_amount,
            daily_max=daily_max, min_bet=min_bet, max_bet=max_bet,
            recent_html=recent_html, ach_html=ach_html,
            lookup_html=lookup_html, lookup_user_id=lookup_user_id,
            lb_config=lb_config, reward_html=reward_html,
            achievement_defs=ACHIEVEMENT_DEFS,
        )

    @app.route('/api/admin/casino/search-users')
    @owner_required
    def api_admin_search_users():
        q = request.args.get('q', '')
        return jsonify(search_users(q))


CASINO_PAGE_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Onichan Casino</title>
<style>
{{ user_css }}
/* === ONICHAN CASINO — mobile-first redesign === */
html, body { overflow-x: hidden; max-width: 100vw; }
body { background: #14081f; }
.main-content { width: 100%; max-width: 100vw; overflow-x: hidden; box-sizing: border-box; }
.casino-wrap { padding: 12px 12px calc(96px + env(safe-area-inset-bottom));
    max-width: 100%; margin: 0 auto; width: 100%;
    box-sizing: border-box; min-height: 100dvh;
    background: linear-gradient(180deg, #1a0a26 0%, #14081f 50%, #0c0418 100%);
    color: #FFFFFF;
    font-family: 'Inter','Nunito','Segoe UI',sans-serif; }
.casino-wrap, .casino-wrap * { box-sizing: border-box; }
.casino-wrap > * { max-width: 100%; }
.casino-title { display: none; }
/* === Hero balance card (replaces old balance-bar + stats-row) === */
.balance-bar { display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px;
    align-items: center;
    background: linear-gradient(135deg, rgba(255,20,147,0.18), rgba(138,43,226,0.18));
    border: 1px solid rgba(255,105,180,0.28);
    padding: 12px 14px; border-radius: 18px; margin-bottom: 12px;
    box-shadow: 0 8px 24px rgba(255,20,147,0.15); }
.bal-item { display: flex; flex-direction: column; min-width: 0; padding: 0; border: none; flex: initial; }
.bal-item:last-of-type { border-right: none; }
.bal-label { font-size: 0.62em; color: #d8b8ee; text-transform: uppercase;
    letter-spacing: 0.6px; font-weight: 700; }
.bal-value { font-size: 1.15em; font-weight: 800; color: #FFF; line-height: 1.2; margin-top: 3px;
    font-variant-numeric: tabular-nums;
    text-shadow: 0 1px 0 rgba(0,0,0,0.4); }
.bal-value.green { color: #4ade80; text-shadow: 0 0 8px rgba(74,222,128,0.4); }
.claim-btn { background: linear-gradient(135deg, #ff1493, #da70d6); color: #fff; border: none;
    padding: 10px 14px; border-radius: 12px; cursor: pointer; font-weight: 800; font-size: 0.74em;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    text-transform: uppercase; letter-spacing: 0.3px; flex-shrink: 0;
    box-shadow: 0 4px 14px rgba(255,20,147,0.45); min-height: 44px;
    white-space: nowrap; }
.claim-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(255,20,147,0.6); }
.claim-btn:disabled { background: rgba(255,105,180,0.18); color: #d8b8ee; cursor: not-allowed; box-shadow: none; }
/* Compact stats strip — single row, pill style */
.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 14px; }
.stat-card { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,105,180,0.18);
    border-radius: 12px; padding: 9px 6px; text-align: center; min-width: 0; }
.stat-label { font-size: 0.58em; color: #d8b8ee; text-transform: uppercase;
    letter-spacing: 0.5px; font-weight: 700; }
.stat-value { font-size: 0.95em; font-weight: 800; color: #fff; margin-top: 3px;
    font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Section heading */
.section-head { display: flex; align-items: center; gap: 8px; margin: 14px 0 10px;
    color: #FFF; font-size: 1.05em; font-weight: 700; }
.section-head::before { content: ''; display: inline-block; width: 4px; height: 18px;
    background: #00E701; border-radius: 2px; }

/* Category pills — pink/purple themed scrollable strip */
.cat-tabs { display: flex; gap: 6px; flex-wrap: nowrap; margin-bottom: 14px; overflow-x: auto;
    padding: 2px 4px 6px 0; -webkit-overflow-scrolling: touch; scrollbar-width: none;
    -webkit-mask-image: linear-gradient(90deg, #000 0, #000 calc(100% - 28px), transparent 100%);
            mask-image: linear-gradient(90deg, #000 0, #000 calc(100% - 28px), transparent 100%); }
.cat-tabs::-webkit-scrollbar { display: none; }
.cat-tab { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,105,180,0.18);
    color: #d8b8ee;
    padding: 9px 14px; border-radius: 999px; cursor: pointer; font-size: 0.78em;
    font-weight: 700; transition: all 0.15s; white-space: nowrap; flex-shrink: 0;
    min-height: 38px; }
.cat-tab:hover { background: rgba(255,105,180,0.12); color: #fff; }
.cat-tab.active { background: linear-gradient(135deg, #ff1493, #da70d6); color: #fff;
    border-color: transparent; box-shadow: 0 4px 12px rgba(255,20,147,0.4); }

/* Game tile grid — square (1:1) tiles, auto-responsive */
.games-grid { display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(110px, calc(33.33% - 8px)), 1fr));
    gap: 10px; margin-bottom: 16px; }
.game-card { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,105,180,0.15);
    border-radius: 14px; cursor: pointer;
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
    overflow: hidden; display: flex; flex-direction: column; position: relative;
    -webkit-tap-highlight-color: transparent; }
.game-card:hover, .game-card:active {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(255,20,147,0.25);
    border-color: rgba(255,105,180,0.5); }
.game-card.disabled { opacity: 0.4; pointer-events: none; filter: grayscale(0.7); }

/* Square tile thumbnail with rich gradient + glow */
.thumb { position: relative; width: 100%; aspect-ratio: 1 / 1; display: flex;
    align-items: center; justify-content: center; overflow: hidden;
    background: linear-gradient(135deg, #2d1b3d, #1a0a26); }
.thumb-icon { font-size: 2.6em; line-height: 1; z-index: 2;
    filter: drop-shadow(0 2px 8px rgba(0,0,0,0.5)); transition: transform 0.25s; }
.game-card:hover .thumb-icon, .game-card:active .thumb-icon { transform: scale(1.12); }
.thumb-shine { position: absolute; top: 0; left: -60%; width: 60%; height: 100%;
    background: linear-gradient(120deg, transparent, rgba(255,255,255,0.18), transparent);
    transform: translateX(-100%); transition: transform 0.8s ease;
    pointer-events: none; z-index: 3; }
.game-card:hover .thumb-shine { transform: translateX(220%); }
/* Subtle inner vignette for depth */
.thumb::before { content: ''; position: absolute; inset: 0; z-index: 1; pointer-events: none;
    background: radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.35) 100%); }
/* No name overlay on the thumb — name lives in card-body for clarity */
.thumb::after { content: none; }
.card-body { padding: 8px 8px 10px; text-align: center;
    background: rgba(0,0,0,0.18);
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; }
.game-card .name { display: block; font-size: 0.72em; font-weight: 700; color: #fff;
    line-height: 1.2; max-width: 100%; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; }
.game-card .edge { font-size: 0.6em; color: #4ade80; font-weight: 700;
    letter-spacing: 0.2px; text-transform: uppercase; }
.game-card .edge::before { content: '● '; font-size: 0.7em; vertical-align: middle; }
/* Per-game themed thumbnails */
.thumb-head_tail .thumb { background: linear-gradient(135deg, #f59e0b, #d97706); }
.thumb-rock_paper_scissors .thumb { background: linear-gradient(135deg, #ef4444, #b91c1c); }
.thumb-spin_wheel .thumb { background: conic-gradient(#ef4444, #fbbf24, #4ade80, #3b82f6, #8b5cf6, #ec4899, #f97316, #ef4444); }
.thumb-number_guess .thumb { background: linear-gradient(135deg, #06b6d4, #0e7490); }
.thumb-dice_rolling .thumb { background: linear-gradient(135deg, #f87171, #dc2626); }
.thumb-card_finding .thumb { background: linear-gradient(135deg, #a78bfa, #7c3aed); }
.thumb-number_slot .thumb { background: linear-gradient(135deg, #fbbf24, #d97706); }
.thumb-number_pool .thumb { background: linear-gradient(135deg, #1f2937, #0f172a); }
.thumb-roulette .thumb { background: conic-gradient(from 90deg, #ef4444, #1f2937, #ef4444, #1f2937, #ef4444, #1f2937, #ef4444, #16a34a, #ef4444); }
.thumb-casino_dice .thumb { background: linear-gradient(135deg, #10b981, #047857); }
.thumb-keno .thumb { background: linear-gradient(135deg, #8b5cf6, #6d28d9); }
.thumb-blackjack .thumb { background: linear-gradient(135deg, #1f2937, #111827); }
.thumb-mines .thumb { background: linear-gradient(135deg, #4b5563, #1f2937); }
.thumb-video_poker .thumb { background: linear-gradient(135deg, #7c3aed, #4c1d95); }
.thumb-color_prediction .thumb { background: linear-gradient(135deg, #ec4899, #be185d); }
.thumb-crazy_times .thumb { background: linear-gradient(135deg, #f97316, #ea580c); }
.thumb-dream_catcher .thumb { background: linear-gradient(135deg, #6366f1, #4338ca); }
.thumb-andar_bahar .thumb { background: linear-gradient(135deg, #b91c1c, #7f1d1d); }
.thumb-pai_gow_poker .thumb { background: linear-gradient(135deg, #be123c, #881337); }
.thumb-crash .thumb { background:
    radial-gradient(ellipse at 30% 90%, rgba(251,191,36,0.4), transparent 50%),
    linear-gradient(180deg, #1e1b4b 0%, #312e81 50%, #7c3aed 100%); }
/* Crash game stage */
.crash-stage { position: relative; height: 260px; margin: 12px 0; border-radius: 14px; overflow: hidden;
    background:
        radial-gradient(ellipse 80% 50% at 50% 100%, rgba(99,102,241,0.45), transparent 70%),
        linear-gradient(180deg, #050218 0%, #1e1b4b 55%, #4c1d95 100%);
    border: 1px solid rgba(139,92,246,0.35);
    box-shadow: inset 0 0 60px rgba(0,0,0,0.5); }
.crash-stars { position: absolute; inset: 0; pointer-events: none;
    background-image:
      radial-gradient(1.5px 1.5px at 12% 18%, #fff, transparent),
      radial-gradient(1px 1px at 58% 32%, #fff, transparent),
      radial-gradient(1.5px 1.5px at 85% 12%, #fbbf24, transparent),
      radial-gradient(1px 1px at 28% 65%, #fff, transparent),
      radial-gradient(1.5px 1.5px at 75% 58%, #ec4899, transparent),
      radial-gradient(1px 1px at 42% 82%, #fff, transparent),
      radial-gradient(1px 1px at 92% 75%, #fff, transparent);
    background-size: 100% 100%; opacity: 0.85; animation: crashTwinkle 3s ease-in-out infinite; }
@keyframes crashTwinkle { 0%,100% { opacity: 0.85; } 50% { opacity: 0.45; } }
/* Animated grid floor for parallax depth */
.crash-stage::before { content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 35%;
    background:
        linear-gradient(180deg, transparent, rgba(139,92,246,0.18)),
        repeating-linear-gradient(90deg, rgba(236,72,153,0.18) 0 2px, transparent 2px 60px),
        repeating-linear-gradient(0deg, rgba(236,72,153,0.18) 0 2px, transparent 2px 30px);
    transform: perspective(180px) rotateX(58deg);
    transform-origin: bottom; opacity: 0.5; pointer-events: none; }

.crash-mult { position: absolute; top: 38%; left: 50%; transform: translate(-50%,-50%);
    font-size: 3.4em; font-weight: 900; color: #fff;
    text-shadow: 0 0 30px rgba(139,92,246,0.95), 0 0 60px rgba(236,72,153,0.55);
    font-variant-numeric: tabular-nums; letter-spacing: 1px; z-index: 5; transition: color 0.3s, transform 0.2s; }
.crash-stage.flying .crash-mult { animation: crashPulse 1.4s ease-in-out infinite; }
@keyframes crashPulse { 0%,100% { transform: translate(-50%,-50%) scale(1); }
    50% { transform: translate(-50%,-50%) scale(1.05);
          text-shadow: 0 0 50px rgba(74,222,128,0.95), 0 0 80px rgba(139,92,246,0.6); } }

/* Aviator-style plane that physically moves on a curve */
.crash-plane { position: absolute; left: 8%; bottom: 14%; font-size: 3em; line-height: 1;
    transform-origin: center; z-index: 4;
    filter: drop-shadow(0 0 12px rgba(251,191,36,0.85)) drop-shadow(0 4px 6px rgba(0,0,0,0.5));
    transition: left 0.12s linear, bottom 0.12s linear, transform 0.12s linear; }
.crash-plane.crashed { animation: crashBoom 0.8s ease-out forwards; }
@keyframes crashBoom {
    0% { transform: scale(1) rotate(-25deg); }
    25% { transform: scale(1.6) rotate(20deg); filter: drop-shadow(0 0 30px #ef4444); }
    60% { transform: scale(2.4) rotate(180deg) translateY(20px); opacity: 0.7; }
    100% { transform: scale(2.6) rotate(360deg) translateY(80px); opacity: 0; }
}

/* SVG curve that draws the actual flight path */
.crash-curve { position: absolute; inset: 0; width: 100%; height: 100%;
    pointer-events: none; z-index: 3; }
.crash-curve path { fill: none; stroke: url(#crashGrad); stroke-width: 4;
    stroke-linecap: round; filter: drop-shadow(0 0 6px rgba(251,191,36,0.8)); }
.crash-curve .fill-path { fill: rgba(239,68,68,0.18); stroke: none; }

.crash-stage.crashed-stage {
    background: radial-gradient(ellipse at 50% 50%, rgba(239,68,68,0.55), transparent 65%),
                linear-gradient(180deg, #1f0a0a 0%, #450a0a 100%);
    animation: crashShake 0.5s; }
@keyframes crashShake { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-8px); } 75% { transform: translateX(8px); } }
.crash-stage.crashed-stage .crash-mult { color: #ef4444 !important; }

/* "Flew away" state when player cashes out — plane keeps flying off-screen */
.crash-plane.escaped { animation: crashEscape 1.4s cubic-bezier(0.25,0.1,0.25,1) forwards; }
@keyframes crashEscape {
    0% { transform: rotate(-25deg); }
    100% { left: 110%; bottom: 110%; transform: rotate(-25deg) scale(0.6); opacity: 0; }
}
/* === STAKE-STYLE MODAL & GAMEPLAY === */
body.casino-modal-open { overflow: hidden; }
.game-modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(15,33,46,0.88); backdrop-filter: blur(6px); z-index: 1000;
    overflow-y: auto; -webkit-overflow-scrolling: touch; }
.game-modal.active { display: flex; align-items: flex-start; justify-content: center;
    padding: 16px 0 60px; }
.game-content { background: #0F212E; border-radius: 8px;
    padding: 18px; max-width: 560px; width: 95%;
    border: 1px solid #2F4553; box-shadow: 0 12px 32px rgba(0,0,0,0.6);
    color: #FFF; font-family: 'Inter','Nunito','Segoe UI',sans-serif; }
.game-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;
    padding-bottom: 12px; border-bottom: 1px solid #2F4553; }
.game-title { font-size: 1.15em; font-weight: 700; color: #FFF; letter-spacing: 0.2px; }
.close-btn { background: #1A2C38; border: 1px solid #2F4553; color: #B1BAD3;
    width: 32px; height: 32px; border-radius: 6px; font-size: 1.2em; cursor: pointer;
    padding: 0; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
.close-btn:hover { background: #213743; color: #FFF; }
.bet-section { margin-bottom: 14px; }
.bet-row { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.bet-input { background: #0F212E; border: 1px solid #2F4553;
    color: #FFF; padding: 10px 12px; border-radius: 4px; font-size: 0.95em;
    width: 110px; font-weight: 600; font-variant-numeric: tabular-nums; }
.bet-input:focus { outline: none; border-color: #00E701; }
.bet-preset { background: #1A2C38; border: 1px solid #2F4553;
    color: #B1BAD3; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-size: 0.82em;
    font-weight: 600; transition: all 0.15s; }
.bet-preset:hover { background: #213743; color: #FFF; border-color: #557086; }
.choice-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
    gap: 8px; margin-bottom: 12px; }
.choice-btn { padding: 12px 14px; border-radius: 4px; border: 1px solid #2F4553;
    background: #1A2C38; color: #FFF; cursor: pointer; font-weight: 600;
    transition: all 0.15s; text-align: center; font-size: 0.88em; }
.choice-btn:hover { background: #213743; border-color: #557086; }
.choice-btn.selected { background: #2F4553; border-color: #00E701;
    box-shadow: 0 0 0 1px #00E701 inset; color: #FFF; }
.play-btn { width: 100%; padding: 14px; border: none; border-radius: 4px; font-size: 1em;
    font-weight: 700; cursor: pointer; color: #0F212E;
    background: #00E701; transition: all 0.15s;
    text-transform: uppercase; letter-spacing: 0.5px; font-family: inherit; }
.play-btn:hover:not(:disabled) { background: #1FFF20; }
.play-btn:disabled { background: #2F4553; color: #B1BAD3; cursor: not-allowed; }
.result-area { min-height: 50px; margin: 12px 0; padding: 14px; border-radius: 6px;
    background: #1A2C38; border: 1px solid #2F4553; text-align: center; }
.result-win { color: #00E701; font-size: 1.2em; font-weight: 700; }
.result-lose { color: #ED4163; font-size: 1.2em; font-weight: 700; }
.result-push { color: #FFD700; font-size: 1.2em; font-weight: 700; }
.free-toggle { display: flex; align-items: center; gap: 10px; margin-bottom: 12px;
    padding: 10px 12px; background: #1A2C38; border: 1px solid #2F4553; border-radius: 4px; }
.free-toggle > span { color: #B1BAD3; font-size: 0.85em; font-weight: 600; }
.toggle-switch { position: relative; width: 38px; height: 22px; flex-shrink: 0; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider { position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: #2F4553; border-radius: 11px; cursor: pointer; transition: 0.2s; }
.toggle-slider:before { content: ''; position: absolute; height: 16px; width: 16px; left: 3px;
    bottom: 3px; background: #FFF; border-radius: 50%; transition: 0.2s; }
.toggle-switch input:checked + .toggle-slider { background: #00E701; }
.toggle-switch input:checked + .toggle-slider:before { transform: translateX(16px); }
.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px; }
.stat-card { background: #1A2C38; border: 1px solid #2F4553; border-radius: 6px;
    padding: 12px 10px; text-align: center; min-width: 0; }
.stat-label { font-size: 0.62em; color: #B1BAD3; text-transform: uppercase;
    letter-spacing: 0.5px; font-weight: 600; }
.stat-value { font-size: 1.05em; font-weight: 700; color: #FFF; margin-top: 4px;
    font-variant-numeric: tabular-nums; }
.mines-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin: 12px 0; }
.mine-cell { aspect-ratio: 1; border-radius: 8px; border: 2px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.08); cursor: pointer; display: flex; align-items: center;
    justify-content: center; font-size: 1.3em; transition: all 0.2s; }
.mine-cell:hover { border-color: #8b5cf6; background: rgba(139,92,246,0.2); }
.mine-cell.gem { background: rgba(74,222,128,0.2); border-color: #4ade80; }
.mine-cell.mine { background: rgba(239,68,68,0.2); border-color: #ef4444; }
.mine-cell.revealed { pointer-events: none; }
.keno-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 4px; margin: 12px 0; }
.keno-num { padding: 6px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.05); cursor: pointer; text-align: center; font-size: 0.8em;
    color: #ccc; transition: all 0.15s; }
.keno-num.selected { background: rgba(139,92,246,0.4); border-color: #8b5cf6; color: #fff; }
.keno-num.hit { background: rgba(74,222,128,0.4); border-color: #4ade80; color: #fff; }
.keno-num.drawn { background: rgba(251,191,36,0.2); border-color: #fbbf24; }
.cards-row { display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; margin: 8px 0; }
.card-display { background: #fff; color: #1a1a2e; padding: 8px 6px; border-radius: 8px;
    min-width: 42px; text-align: center; font-weight: 700; font-size: 1em;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3); }
.card-display.red { color: #ef4444; }
.card-display.hidden-card { background: linear-gradient(135deg, #8b5cf6, #6366f1); color: #fff; }
.tab-bar { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; }
.tab-btn { background: none; border: none; color: #aaa; padding: 8px 16px; cursor: pointer;
    font-size: 0.85em; border-radius: 8px 8px 0 0; transition: all 0.2s; }
.tab-btn.active { color: #fff; background: rgba(139,92,246,0.3); }
@media(max-width:600px) {
    .games-grid { gap: 8px; }
    .game-card { border-radius: 12px; }
    .thumb-icon { font-size: 2.2em; }
    .game-card .name { font-size: 0.68em; }
    .game-card .edge { font-size: 0.55em; }
    .card-body { padding: 6px 6px 8px; }
    .game-content { padding: 14px; max-height: 95vh; }
    .casino-wrap { padding: 10px 10px calc(96px + env(safe-area-inset-bottom)); }
    .balance-bar { padding: 10px 12px; gap: 8px; border-radius: 14px; }
    .bal-value { font-size: 1.05em; }
    .bal-label { font-size: 0.58em; }
    .keno-grid { grid-template-columns: repeat(8, 1fr); }
    .keno-num { font-size: 0.7em; padding: 4px; }
    .stat-card { padding: 8px 6px; border-radius: 10px; }
    .stat-label { font-size: 0.55em; letter-spacing: 0.3px; }
    .stat-value { font-size: 0.92em; }
    .stats-row { gap: 6px; margin-bottom: 12px; }
    .cat-tabs { gap: 6px; margin-bottom: 12px; }
    .cat-tab { padding: 8px 13px; font-size: 0.74em; min-height: 36px; }
    .tab-bar { gap: 2px; padding-bottom: 6px; margin-bottom: 12px;
        overflow-x: auto; -webkit-overflow-scrolling: touch; }
    .tab-btn { padding: 7px 12px; font-size: 0.78em; flex-shrink: 0; white-space: nowrap; }
    .claim-btn { padding: 9px 12px; font-size: 0.7em; }
}
@media(max-width:400px) {
    .games-grid { gap: 6px; }
    .thumb-icon { font-size: 2.2em; }
    .game-card .name { font-size: 0.68em; }
    .game-card .edge { font-size: 0.55em; }
    .stat-label { font-size: 0.52em; }
    .stat-value { font-size: 0.85em; }
    .bal-label { font-size: 0.55em; }
    .bal-value { font-size: 0.95em; }
    .balance-bar { grid-template-columns: 1fr 1fr; padding: 10px 12px; }
    .claim-btn { grid-column: 1 / -1; width: 100%; padding: 10px; font-size: 0.75em; }
    .cat-tab { padding: 7px 11px; font-size: 0.7em; }
}
/* === High-Quality Game Animations === */
.anim-stage { min-height: 130px; display: flex; align-items: center; justify-content: center;
    margin: 12px 0; padding: 16px;
    background: radial-gradient(ellipse at center, rgba(139,92,246,0.10), rgba(0,0,0,0.45));
    border: 1px solid rgba(139,92,246,0.18);
    border-radius: 16px; position: relative; overflow: hidden;
    box-shadow: inset 0 0 30px rgba(0,0,0,0.4); }
.anim-stage::before { content: ''; position: absolute; inset: 0;
    background: radial-gradient(circle at 20% 30%, rgba(236,72,153,0.06), transparent 40%),
                radial-gradient(circle at 80% 70%, rgba(74,222,128,0.06), transparent 40%);
    pointer-events: none; }
.spin-loader { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff; border-radius: 50%; animation: spinLoad 0.7s linear infinite;
    vertical-align: middle; margin-right: 6px; }
@keyframes spinLoad { to { transform: rotate(360deg) } }
.pulse-loader { width: 60px; height: 60px; border-radius: 50%;
    background: radial-gradient(circle, #8b5cf6, #ec4899);
    box-shadow: 0 0 30px rgba(139,92,246,0.7); animation: pulseLoad 1s ease infinite; }
@keyframes pulseLoad { 0%,100%{transform:scale(0.85);opacity:0.7} 50%{transform:scale(1.1);opacity:1} }
.keno-balls-pre { display: flex; gap: 8px; }
.keno-balls-pre span { width: 16px; height: 16px; border-radius: 50%;
    background: linear-gradient(135deg, #fbbf24, #f59e0b); box-shadow: 0 0 8px rgba(251,191,36,0.7);
    animation: ballBounce 0.8s ease infinite; }
.keno-balls-pre span:nth-child(2) { animation-delay: 0.1s }
.keno-balls-pre span:nth-child(3) { animation-delay: 0.2s }
.keno-balls-pre span:nth-child(4) { animation-delay: 0.3s }
.keno-balls-pre span:nth-child(5) { animation-delay: 0.4s }
@keyframes ballBounce { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-12px)} }
.coin { width: 80px; height: 80px; border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, #fef3c7, #fcd34d 40%, #f59e0b 80%);
    border: 4px solid #d97706; display: flex; align-items: center; justify-content: center;
    font-size: 1.8em; font-weight: 900; color: #78350f;
    box-shadow: 0 8px 28px rgba(245,158,11,0.6), inset 0 -4px 8px rgba(120,53,15,0.3),
                inset 0 4px 8px rgba(255,255,255,0.4);
    text-shadow: 0 2px 3px rgba(255,255,255,0.4); position: relative; z-index: 1; }
.coin.flipping { animation: coinFlip 1.4s cubic-bezier(0.4, 0, 0.2, 1); }
@keyframes coinFlip {
    0%{transform:rotateY(0) translateY(0)}
    25%{transform:rotateY(900deg) translateY(-30px)}
    50%{transform:rotateY(1800deg) translateY(0)}
    75%{transform:rotateY(2700deg) translateY(-15px)}
    100%{transform:rotateY(3600deg) translateY(0)}
}
.dice { width: 60px; height: 60px;
    background: linear-gradient(135deg, #ffffff, #e5e7eb);
    border-radius: 12px; display: inline-flex;
    align-items: center; justify-content: center; font-size: 1.9em; font-weight: 900; color: #1a1a2e;
    box-shadow: 0 6px 14px rgba(0,0,0,0.5), inset 0 -3px 6px rgba(0,0,0,0.1),
                inset 0 3px 6px rgba(255,255,255,0.8);
    margin: 0 6px; position: relative; z-index: 1; }
.dice.rolling { animation: diceRoll 1.2s cubic-bezier(0.36, 0.07, 0.19, 0.97); }
@keyframes diceRoll {
    0%{transform:rotate(0) translateY(0) scale(1)}
    20%{transform:rotate(216deg) translateY(-30px) scale(1.15)}
    40%{transform:rotate(540deg) translateY(0) scale(1)}
    60%{transform:rotate(900deg) translateY(-22px) scale(1.1)}
    80%{transform:rotate(1260deg) translateY(0) scale(1)}
    100%{transform:rotate(1440deg) translateY(0) scale(1)}
}
.wheel { width: 160px; height: 160px; border-radius: 50%; position: relative;
    background: conic-gradient(#ef4444 0deg 45deg,#fbbf24 45deg 90deg,#4ade80 90deg 135deg,#3b82f6 135deg 180deg,#8b5cf6 180deg 225deg,#ec4899 225deg 270deg,#f97316 270deg 315deg,#10b981 315deg 360deg);
    border: 6px solid #fbbf24;
    box-shadow: 0 0 40px rgba(139,92,246,0.6), inset 0 0 20px rgba(0,0,0,0.4),
                0 6px 18px rgba(0,0,0,0.5);
    transition: transform 3s cubic-bezier(.17,.67,.35,1); z-index: 1; }
.wheel::after { content: ''; position: absolute; top: 50%; left: 50%; width: 24px; height: 24px;
    border-radius: 50%; background: radial-gradient(circle, #fff, #fbbf24);
    transform: translate(-50%, -50%); box-shadow: 0 0 10px rgba(251,191,36,0.8); }
.wheel.spinning-pre { transition: transform 0.8s cubic-bezier(0.4, 0, 0.6, 1); }
.wheel-pointer { position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
    width: 0; height: 0; border-left: 10px solid transparent; border-right: 10px solid transparent;
    border-top: 18px solid #fbbf24; z-index: 2; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.4)); }
.wheel-wrap { position: relative; display: inline-block; }
.slot-reels { display: flex; gap: 6px; justify-content: center; }
.slot-reel { width: 60px; height: 70px; background: #fff; border-radius: 8px; overflow: hidden;
    display: flex; align-items: center; justify-content: center; font-size: 2em; font-weight: 900;
    color: #1a1a2e; box-shadow: inset 0 0 10px rgba(0,0,0,0.3); }
.slot-reel.spinning { animation: slotSpin 0.08s linear infinite; }
@keyframes slotSpin { 0%{transform:translateY(-15px)} 100%{transform:translateY(15px)} }
.flip-card { width: 50px; height: 70px; perspective: 600px; display: inline-block; margin: 0 3px; }
.flip-inner { position: relative; width: 100%; height: 100%; transition: transform 0.6s; transform-style: preserve-3d; }
.flip-card.flipped .flip-inner { transform: rotateY(180deg); }
.flip-front, .flip-back { position: absolute; width: 100%; height: 100%; backface-visibility: hidden;
    border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 1em; }
.flip-front { background: linear-gradient(135deg, #8b5cf6, #6366f1); color: #fff; }
.flip-back { background: #fff; color: #1a1a2e; transform: rotateY(180deg); box-shadow: 0 2px 8px rgba(0,0,0,0.3); }
.flip-back.red { color: #ef4444; }
.spin-num { font-size: 3em; font-weight: 900; color: #fbbf24; text-shadow: 0 0 20px rgba(251,191,36,0.6);
    animation: numCycle 0.1s linear infinite; }
@keyframes numCycle { 0%{transform:scale(1)} 50%{transform:scale(1.1)} 100%{transform:scale(1)} }
.color-orb { width: 80px; height: 80px; border-radius: 50%; box-shadow: 0 0 30px currentColor;
    transition: background 0.2s; animation: pulse 0.4s ease infinite; }
@keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.1)} }
.rps-hand { font-size: 4em; animation: rpsBounce 0.5s ease infinite; }
@keyframes rpsBounce { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-15px)} }
.win-glow { animation: winGlow 1.2s ease infinite; }
@keyframes winGlow { 0%,100%{text-shadow:0 0 8px #4ade80} 50%{text-shadow:0 0 25px #4ade80,0 0 40px #4ade80} }
</style>
</head><body>
{{ sidebar|safe }}
<div class="main-content"><div class="casino-wrap">
<div class="balance-bar">
    <div class="bal-item"><span class="bal-label">Balance</span><span class="bal-value" id="balance">${{ balance }}</span></div>
    <div class="bal-item"><span class="bal-label">Free Credits</span><span class="bal-value green" id="freeBalance">${{ free_balance }}</span></div>
    <div style="margin-left:auto">
        <button class="claim-btn" id="claimBtn" onclick="claimDaily()" {% if can_claim != 'true' %}disabled{% endif %}>
            {% if can_claim == 'true' %}Claim ${{ daily_amount }} Free{% else %}Next: {{ next_claim }}{% endif %}
        </button>
    </div>
</div>

<div class="stats-row">
    <div class="stat-card"><div class="stat-label">Total Bets</div><div class="stat-value">{{ total_bets }}</div></div>
    <div class="stat-card"><div class="stat-label">Wagered</div><div class="stat-value">${{ total_wagered }}</div></div>
    <div class="stat-card"><div class="stat-label">Won</div><div class="stat-value">${{ total_won }}</div></div>
</div>

<div class="cat-tabs" id="catTabs">{{ cat_tabs|safe }}</div>
<div class="games-grid" id="gamesGrid">{{ games_html_cards|safe }}</div>

<div class="tab-bar">
    <button class="tab-btn active" onclick="showPanel('history')">History</button>
    <button class="tab-btn" onclick="showPanel('leaderboard')">Leaderboard</button>
    <button class="tab-btn" onclick="showPanel('achievements')">Achievements</button>
</div>
<div id="panelArea" style="min-height:200px;background:rgba(0,0,0,0.2);border-radius:12px;padding:16px">
    <div style="color:#aaa;text-align:center">Loading...</div>
</div>
</div></div>

<div class="game-modal" id="gameModal">
    <div class="game-content" id="gameContent"></div>
</div>

<script>
var GAMES_META = {
    head_tail: {name:'Head & Tail',icon:'&#x1FA99;',type:'choice',choices:['head','tail'],choiceLabels:{head:'&#x1FA99; Head',tail:'&#x1FA99; Tail'}},
    rock_paper_scissors: {name:'Rock Paper Scissors',icon:'&#x270A;',type:'choice',choices:['rock','paper','scissors'],choiceLabels:{rock:'&#x1FAA8; Rock',paper:'&#x1F4C4; Paper',scissors:'&#x2702; Scissors'}},
    spin_wheel: {name:'Spin Wheel',icon:'&#x1F3A1;',type:'simple'},
    number_guess: {name:'Number Guess',icon:'&#x1F522;',type:'number_input',inputLabel:'Guess (1-99)',inputKey:'guess_number'},
    dice_rolling: {name:'Dice Rolling',icon:'&#x1F3B2;',type:'choice',choices:['high','low','seven'],choiceLabels:{high:'&#x2B06; High (8+)',low:'&#x2B07; Low (2-6)',seven:'7&#xFE0F;&#x20E3; Seven'}},
    card_finding: {name:'Card Finding',icon:'&#x1F0CF;',type:'position',positions:3},
    number_slot: {name:'Number Slot',icon:'&#x1F3B0;',type:'simple'},
    number_pool: {name:'Number Pool',icon:'&#x1F3B1;',type:'choice',choices:['odd','even'],choiceLabels:{odd:'Odd',even:'Even'}},
    roulette: {name:'Roulette',icon:'&#x1F3A1;',type:'roulette'},
    casino_dice: {name:'Casino Dice',icon:'&#x1F3B2;',type:'casino_dice'},
    keno: {name:'Keno',icon:'&#x1F522;',type:'keno'},
    blackjack: {name:'Blackjack',icon:'&#x1F0CF;',type:'blackjack'},
    mines: {name:'Mines',icon:'&#x1F4A3;',type:'mines'},
    poker: {name:'Video Poker',icon:'&#x2660;',type:'poker'},
    color_prediction: {name:'Color Prediction',icon:'&#x1F3A8;',type:'choice',choices:['red','green','blue'],choiceLabels:{red:'&#x1F534; Red',green:'&#x1F7E2; Green',blue:'&#x1F535; Blue'}},
    crazy_times: {name:'Crazy Times',icon:'&#x1F92A;',type:'choice',choices:['1','2','5','10','coin_flip','pachinko','cash_hunt','crazy_times'],choiceLabels:{'1':'1x','2':'2x','5':'5x','10':'10x',coin_flip:'Coin Flip',pachinko:'Pachinko',cash_hunt:'Cash Hunt',crazy_times:'Crazy Times'}},
    dream_catcher: {name:'Dream Catcher',icon:'&#x1F319;',type:'choice',choices:['1','2','5','10','20','40'],choiceLabels:{'1':'1x','2':'2x','5':'5x','10':'10x','20':'20x','40':'40x'}},
    andar_bahar: {name:'Andar Bahar',icon:'&#x1F3B4;',type:'choice',choices:['andar','bahar'],choiceLabels:{andar:'Andar',bahar:'Bahar'}},
    pai_gow_poker: {name:'Pai Gow Poker',icon:'&#x1F004;',type:'simple'},
    crash: {name:'Crash',icon:'&#x1F680;',type:'crash'}
};
var CATEGORIES = {{ categories_json|safe }};
var currentGame = null;
var currentChoice = null;
var currentSession = null;
var isFreePlay = false;

// === Audio System ===
var SOUND_BASE = '/static/casino/audio/';
var SOUNDS = {};
var SOUND_FILES = {
    coin:'coin.mp3', dice:'casino-dice.mp3', spin:'spin.mp3', wheel:'spin-wheel.mp3',
    slot:'number-slot.mp3', card:'card.mp3', cardflip:'card-flip.mp3', mine:'mine.mp3',
    pool:'pool.mp3', keno:'keno.wav', kenoStart:'keno_start.wav', rps:'rock-paper.mp3',
    click:'click.mp3', win:'win.wav', lose:'lose.wav', start:'start.mp3'
};
function playSound(key) {
    try {
        if (!SOUNDS[key]) {
            var f = SOUND_FILES[key]; if (!f) return;
            SOUNDS[key] = new Audio(SOUND_BASE + f);
            SOUNDS[key].volume = 0.55;
        }
        SOUNDS[key].pause(); SOUNDS[key].currentTime = 0;
        var p = SOUNDS[key].play();
        if (p && p.catch) p.catch(function(){});
    } catch(e) {}
}
function stopSound(key) {
    try { if (SOUNDS[key]) { SOUNDS[key].pause(); SOUNDS[key].currentTime = 0; } } catch(e){}
}

function openGame(gid) {
    currentGame = gid;
    currentChoice = null;
    currentSession = null;
    var m = GAMES_META[gid];
    if (!m) return;
    var html = '<div class="game-header"><span class="game-title">' + m.icon + ' ' + m.name + '</span><button class="close-btn" onclick="closeGame()">&times;</button></div>';
    html += '<div class="free-toggle"><label class="toggle-switch"><input type="checkbox" id="freeToggle" onchange="isFreePlay=this.checked"><span class="toggle-slider"></span></label><span style="color:#aaa;font-size:0.85em">Free Play</span></div>';
    html += '<div class="bet-section"><div class="bet-row"><input type="number" class="bet-input" id="betInput" value="1.00" min="0.10" step="0.10"><div class="bet-preset" onclick="setBet(0.5)">$0.50</div><div class="bet-preset" onclick="setBet(1)">$1</div><div class="bet-preset" onclick="setBet(5)">$5</div><div class="bet-preset" onclick="setBet(10)">$10</div></div></div>';
    if (m.type === 'choice') {
        html += '<div class="choice-grid" id="choiceGrid">';
        for (var i = 0; i < m.choices.length; i++) {
            var c = m.choices[i];
            var label = m.choiceLabels[c] || c;
            html += '<div class="choice-btn" data-choice="' + c + '" onclick="selectChoice(this, \'' + c + '\')">' + label + '</div>';
        }
        html += '</div>';
        currentChoice = m.choices[0];
    } else if (m.type === 'number_input') {
        html += '<div style="margin-bottom:12px"><label style="color:#aaa;font-size:0.85em">' + m.inputLabel + '</label><input type="number" class="bet-input" id="gameInput" value="50" min="1" max="99" style="width:100%;margin-top:4px"></div>';
    } else if (m.type === 'position') {
        html += '<div class="choice-grid" id="posGrid">';
        for (var p = 0; p < m.positions; p++) {
            html += '<div class="choice-btn" data-pos="' + p + '" onclick="selectPos(this,' + p + ')">Card ' + (p+1) + '</div>';
        }
        html += '</div>';
        currentChoice = 0;
    } else if (m.type === 'roulette') {
        html += buildRouletteUI();
    } else if (m.type === 'casino_dice') {
        html += buildCasinoDiceUI();
    } else if (m.type === 'keno') {
        html += buildKenoUI();
    } else if (m.type === 'blackjack') {
        html += '<div id="bjArea"></div>';
    } else if (m.type === 'mines') {
        html += buildMinesUI();
    } else if (m.type === 'poker') {
        html += '<div id="pokerArea"></div>';
    } else if (m.type === 'crash') {
        html += buildCrashUI();
    }
    html += '<button class="play-btn" id="playBtn" onclick="playGame()">Play</button>';
    html += '<div class="result-area" id="resultArea"></div>';
    document.getElementById('gameContent').innerHTML = html;
    document.getElementById('gameModal').classList.add('active');
    document.body.classList.add('casino-modal-open');
    document.getElementById('gameModal').scrollTop = 0;
    playSound('start');
    if (m.type === 'choice' && m.choices.length > 0) {
        var first = document.querySelector('#choiceGrid .choice-btn');
        if (first) first.classList.add('selected');
    }
    if (m.type === 'position') {
        var fp = document.querySelector('#posGrid .choice-btn');
        if (fp) fp.classList.add('selected');
    }
}

function closeGame() {
    document.getElementById('gameModal').classList.remove('active');
    document.body.classList.remove('casino-modal-open');
    if (typeof crashTimer !== 'undefined' && crashTimer) { clearInterval(crashTimer); crashTimer = null; }
    currentGame = null;
    currentSession = null;
}

function setBet(v) { document.getElementById('betInput').value = v.toFixed(2); playSound('click'); }
function selectChoice(el, c) {
    currentChoice = c; playSound('click');
    var btns = el.parentElement.querySelectorAll('.choice-btn');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('selected');
    el.classList.add('selected');
}
function selectPos(el, p) {
    currentChoice = p; playSound('click');
    var btns = el.parentElement.querySelectorAll('.choice-btn');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('selected');
    el.classList.add('selected');
}

function switchTab(cat) {
    var tabs = document.querySelectorAll('.cat-tab');
    for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
    event.target.classList.add('active');
    var cards = document.querySelectorAll('.game-card');
    if (cat === 'all') {
        for (var i = 0; i < cards.length; i++) cards[i].style.display = '';
        return;
    }
    var catGames = CATEGORIES[cat] || [];
    for (var i = 0; i < cards.length; i++) {
        var gid = cards[i].getAttribute('onclick').match(/'([^']+)'/)[1];
        cards[i].style.display = catGames.indexOf(gid) >= 0 ? '' : 'none';
    }
}

function buildRouletteUI() {
    var html = '<div class="choice-grid" id="choiceGrid">';
    var opts = [{v:'red',l:'&#x1F534; Red'},{v:'black',l:'&#x26AB; Black'},{v:'odd',l:'Odd'},{v:'even',l:'Even'},{v:'low',l:'1-18'},{v:'high',l:'19-36'},{v:'dozen1',l:'1-12'},{v:'dozen2',l:'13-24'},{v:'dozen3',l:'25-36'}];
    for (var i = 0; i < opts.length; i++) {
        html += '<div class="choice-btn" data-choice="' + opts[i].v + '" onclick="selectChoice(this,\'' + opts[i].v + '\')">' + opts[i].l + '</div>';
    }
    html += '</div>';
    html += '<div style="margin-bottom:12px"><label style="color:#aaa;font-size:0.85em">Or pick a number (0-36):</label><input type="number" class="bet-input" id="rouletteNumber" min="0" max="36" style="width:80px;margin-left:8px"></div>';
    currentChoice = 'red';
    return html;
}

function buildCasinoDiceUI() {
    var html = '<div style="margin-bottom:12px"><label style="color:#aaa;font-size:0.85em">Win Chance %</label><input type="range" id="dicePercent" min="1" max="95" value="50" style="width:100%" oninput="updateDiceDisplay()"><div style="display:flex;justify-content:space-between;color:#aaa;font-size:0.8em"><span id="dicePercentLabel">50%</span><span id="dicePayoutLabel">1.98x</span></div></div>';
    html += '<div class="choice-grid" id="choiceGrid"><div class="choice-btn selected" onclick="selectChoice(this,\'low\')">Roll Low</div><div class="choice-btn" onclick="selectChoice(this,\'high\')">Roll High</div></div>';
    currentChoice = 'low';
    return html;
}

function updateDiceDisplay() {
    var p = document.getElementById('dicePercent').value;
    document.getElementById('dicePercentLabel').textContent = p + '%';
    document.getElementById('dicePayoutLabel').textContent = (99/p).toFixed(4) + 'x';
}

function buildKenoUI() {
    var html = '<div style="color:#aaa;font-size:0.85em;margin-bottom:8px">Pick 1-10 numbers:</div><div class="keno-grid" id="kenoGrid">';
    for (var i = 1; i <= 80; i++) {
        html += '<div class="keno-num" onclick="toggleKeno(this,' + i + ')">' + i + '</div>';
    }
    html += '</div>';
    return html;
}
var kenoPicks = [];
function toggleKeno(el, n) {
    var idx = kenoPicks.indexOf(n);
    if (idx >= 0) { kenoPicks.splice(idx,1); el.classList.remove('selected'); }
    else if (kenoPicks.length < 10) { kenoPicks.push(n); el.classList.add('selected'); }
    playSound('click');
}

function buildMinesUI() {
    var html = '<div style="margin-bottom:12px"><label style="color:#aaa;font-size:0.85em">Number of Mines:</label><select id="minesCount" style="background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);color:#fff;padding:6px;border-radius:8px;margin-left:8px">';
    for (var i = 1; i <= 24; i++) html += '<option value="' + i + '"' + (i===3?' selected':'') + '>' + i + '</option>';
    html += '</select></div><div class="mines-grid" id="minesGrid"></div>';
    html += '<div id="minesInfo" style="text-align:center;color:#aaa;font-size:0.85em"></div>';
    html += '<button class="play-btn" id="cashoutBtn" style="display:none;background:linear-gradient(135deg,#4ade80,#22c55e);margin-top:8px" onclick="minesCashout()">Cash Out</button>';
    return html;
}

function playGame() {
    var m = GAMES_META[currentGame];
    if (!m) return;
    var btn = document.getElementById('playBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin-loader"></span> Playing...';
    var bet = parseFloat(document.getElementById('betInput').value) || 1;
    var body = {game: currentGame, bet: bet, free_play: isFreePlay};

    if (m.type === 'choice') body.choose = currentChoice;
    else if (m.type === 'number_input') body[m.inputKey] = document.getElementById('gameInput').value;
    else if (m.type === 'position') body.position = currentChoice;
    else if (m.type === 'roulette') {
        var numEl = document.getElementById('rouletteNumber');
        if (numEl && numEl.value !== '') { body.bet_type = 'number'; body.bet_value = numEl.value; }
        else { body.bet_type = currentChoice || 'red'; }
    }
    else if (m.type === 'casino_dice') {
        body.percent = document.getElementById('dicePercent').value;
        body.choose = currentChoice || 'low';
    }
    else if (m.type === 'keno') { body.picks = kenoPicks; }
    else if (m.type === 'blackjack') { body.action = 'deal'; }
    else if (m.type === 'mines') {
        body.action = 'start';
        body.num_mines = parseInt(document.getElementById('minesCount').value) || 3;
    }
    else if (m.type === 'poker') { body.action = 'deal'; }
    else if (m.type === 'crash') {
        body.action = 'start';
        var ac = document.getElementById('crashAuto');
        if (ac && ac.value && parseFloat(ac.value) >= 1.01) body.auto_cashout = parseFloat(ac.value);
    }

    /* INSTANT pre-bet animation — fires the moment you click Play */
    startPreAnim(currentGame);
    var animStart = Date.now();
    var MIN_ANIM = 800; /* ensure user sees the animation even on a fast network */

    fetch('/api/casino/play', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})
    .then(function(r){return r.json()})
    .then(function(data){
        var elapsed = Date.now() - animStart;
        var wait = Math.max(0, MIN_ANIM - elapsed);
        setTimeout(function(){
            if (data.error) { btn.disabled=false; btn.textContent='Play'; showResult(data.error, 'lose'); return; }
            updateBalances(data);
            if (m.type === 'blackjack') { btn.disabled=false; btn.textContent='Play'; handleBlackjack(data); return; }
            if (m.type === 'mines') { btn.disabled=false; btn.textContent='Play'; handleMinesStart(data); return; }
            if (m.type === 'poker') { btn.disabled=false; btn.textContent='Play'; handlePokerDeal(data); return; }
            if (m.type === 'crash') { btn.disabled=false; btn.textContent='Play'; handleCrashStart(data); return; }
            playAnimation(currentGame, data, function(){
                btn.disabled = false;
                btn.textContent = 'Play';
                showGameResult(data);
            });
        }, wait);
    })
    .catch(function(e){ btn.disabled=false; btn.textContent='Play'; showResult('Network error','lose'); });
}

/* Instant pre-bet placeholder animation — runs the moment Play is clicked */
function startPreAnim(game) {
    var ra = document.getElementById('resultArea');
    if (!ra) return;
    var html = '';
    if (game === 'head_tail') html = '<div class="anim-stage"><div class="coin flipping">?</div></div>';
    else if (game === 'rock_paper_scissors') html = '<div class="anim-stage" style="gap:20px"><div class="rps-hand">✊</div><div style="color:#aaa;font-size:1.5em">VS</div><div class="rps-hand">✊</div></div>';
    else if (game === 'dice_rolling' || game === 'casino_dice') html = '<div class="anim-stage"><div class="dice rolling">?</div><div class="dice rolling">?</div></div>';
    else if (game === 'spin_wheel' || game === 'roulette' || game === 'dream_catcher' || game === 'crazy_times') {
        html = '<div class="anim-stage"><div class="wheel-wrap"><div class="wheel-pointer"></div><div class="wheel spinning-pre"></div></div></div>';
    }
    else if (game === 'number_slot') html = '<div class="anim-stage"><div class="slot-reels"><div class="slot-reel spinning">?</div><div class="slot-reel spinning">?</div><div class="slot-reel spinning">?</div></div></div>';
    else if (game === 'number_guess' || game === 'number_pool') html = '<div class="anim-stage"><div class="spin-num">?</div></div>';
    else if (game === 'color_prediction') html = '<div class="anim-stage"><div class="color-orb" style="background:#8b5cf6"></div></div>';
    else if (game === 'card_finding' || game === 'andar_bahar' || game === 'pai_gow_poker') html = '<div class="anim-stage"><div class="flip-card"><div class="flip-inner"><div class="flip-front">?</div><div class="flip-back">?</div></div></div></div>';
    else if (game === 'keno') html = '<div class="anim-stage" style="flex-direction:column;gap:8px"><div style="color:#fbbf24;font-weight:700">Drawing balls...</div><div class="keno-balls-pre"><span></span><span></span><span></span><span></span><span></span></div></div>';
    else html = '<div class="anim-stage"><div class="pulse-loader"></div></div>';
    ra.innerHTML = html;
    /* Trigger wheel pre-spin */
    var w = ra.querySelector('.wheel.spinning-pre');
    if (w) requestAnimationFrame(function(){ w.style.transform = 'rotate(720deg)'; });
}

function playAnimation(game, data, done) {
    var ra = document.getElementById('resultArea');
    if (!ra) { done(); return; }
    var stage = '';
    var delay = 1500;
    if (game === 'head_tail') {
        stage = '<div class="anim-stage"><div class="coin flipping" id="animCoin">?</div></div>';
        ra.innerHTML = stage;
        playSound('coin');
        setTimeout(function(){
            var c = document.getElementById('animCoin');
            if (c) { c.classList.remove('flipping'); c.textContent = (data.coin_result||'').charAt(0).toUpperCase(); }
            setTimeout(done, 400);
        }, 1400);
        return;
    }
    if (game === 'rock_paper_scissors') {
        stage = '<div class="anim-stage" style="gap:24px"><div class="rps-hand" id="rpsP">✊</div><div style="color:#aaa;font-size:1.5em">VS</div><div class="rps-hand" id="rpsB">✊</div></div>';
        ra.innerHTML = stage;
        playSound('rps');
        var emoji = {rock:'✊', paper:'✋', scissors:'✌️'};
        setTimeout(function(){
            var p = document.getElementById('rpsP'), b = document.getElementById('rpsB');
            if (p) { p.style.animation='none'; p.textContent = emoji[data.player_choice||'rock']; }
            if (b) { b.style.animation='none'; b.textContent = emoji[data.bot_choice||'rock']; }
            setTimeout(done, 500);
        }, 1200);
        return;
    }
    if (game === 'dice_rolling' || game === 'casino_dice') {
        var dice = data.dice || [data.roll];
        var html = '<div class="anim-stage">';
        for (var i = 0; i < dice.length; i++) html += '<div class="dice rolling" id="d'+i+'">?</div>';
        html += '</div>';
        ra.innerHTML = html;
        playSound('dice');
        setTimeout(function(){
            for (var i = 0; i < dice.length; i++) {
                var d = document.getElementById('d'+i);
                if (d) { d.classList.remove('rolling'); d.textContent = dice[i]; }
            }
            setTimeout(done, 400);
        }, 1200);
        return;
    }
    if (game === 'spin_wheel' || game === 'roulette' || game === 'dream_catcher' || game === 'crazy_times') {
        stage = '<div class="anim-stage"><div class="wheel-wrap"><div class="wheel-pointer"></div><div class="wheel" id="animWheel"></div></div></div>';
        ra.innerHTML = stage;
        playSound('wheel');
        var w = document.getElementById('animWheel');
        if (w) {
            var deg = 1440 + Math.floor(Math.random()*360);
            requestAnimationFrame(function(){ w.style.transform = 'rotate('+deg+'deg)'; });
        }
        setTimeout(done, 3100);
        return;
    }
    if (game === 'number_slot') {
        var reels = data.reels || ['?','?','?'];
        var html = '<div class="anim-stage"><div class="slot-reels">';
        for (var i = 0; i < reels.length; i++) html += '<div class="slot-reel spinning" id="r'+i+'">?</div>';
        html += '</div></div>';
        ra.innerHTML = html;
        playSound('slot');
        for (var i = 0; i < reels.length; i++) {
            (function(idx){
                setTimeout(function(){
                    var r = document.getElementById('r'+idx);
                    if (r) { r.classList.remove('spinning'); r.textContent = reels[idx]; }
                    playSound('click');
                }, 600 + idx*400);
            })(i);
        }
        setTimeout(done, 600 + reels.length*400 + 200);
        return;
    }
    if (game === 'number_guess' || game === 'number_pool') {
        stage = '<div class="anim-stage"><div class="spin-num" id="spinN">0</div></div>';
        ra.innerHTML = stage;
        playSound(game === 'number_pool' ? 'pool' : 'spin');
        var target = data.secret !== undefined ? data.secret : data.ball;
        var max = game === 'number_guess' ? 100 : 9;
        var el = document.getElementById('spinN');
        var iv = setInterval(function(){ if (el) el.textContent = Math.floor(Math.random()*(max+1)); }, 80);
        setTimeout(function(){
            clearInterval(iv);
            if (el) { el.style.animation='none'; el.textContent = target; }
            setTimeout(done, 400);
        }, 1500);
        return;
    }
    if (game === 'color_prediction') {
        stage = '<div class="anim-stage"><div class="color-orb" id="orb" style="background:#888;color:#888"></div></div>';
        ra.innerHTML = stage;
        playSound('spin');
        var colors = ['#ef4444','#4ade80','#3b82f6'];
        var orb = document.getElementById('orb');
        var iv = setInterval(function(){ if(orb){var c=colors[Math.floor(Math.random()*3)]; orb.style.background=c; orb.style.color=c;} }, 100);
        setTimeout(function(){
            clearInterval(iv);
            var cmap = {red:'#ef4444', green:'#4ade80', blue:'#3b82f6'};
            if (orb) { orb.style.animation='none'; var c = cmap[data.winning_color]||'#888'; orb.style.background=c; orb.style.color=c; }
            setTimeout(done, 400);
        }, 1500);
        return;
    }
    if (game === 'card_finding' || game === 'andar_bahar' || game === 'pai_gow_poker') {
        var cards = [];
        if (game === 'card_finding') cards = (data.cards||[]).map(function(c){return {face:c, red: c.indexOf('♥')>=0||c.indexOf('♦')>=0};});
        else if (game === 'andar_bahar') cards = [{face:data.joker, red:(data.joker||'').indexOf('♥')>=0||(data.joker||'').indexOf('♦')>=0}];
        else if (game === 'pai_gow_poker') cards = (data.player_high||[]).slice(0,5).map(function(c){return {face:c, red:c.indexOf('♥')>=0||c.indexOf('♦')>=0};});
        if (cards.length === 0) { done(); return; }
        var html = '<div class="anim-stage" style="flex-wrap:wrap">';
        for (var i = 0; i < cards.length; i++) {
            html += '<div class="flip-card" id="fc'+i+'"><div class="flip-inner"><div class="flip-front">?</div><div class="flip-back'+(cards[i].red?' red':'')+'">'+cards[i].face+'</div></div></div>';
        }
        html += '</div>';
        ra.innerHTML = html;
        for (var i = 0; i < cards.length; i++) {
            (function(idx){
                setTimeout(function(){
                    var c = document.getElementById('fc'+idx);
                    if (c) c.classList.add('flipped');
                    playSound('cardflip');
                }, 200 + idx*180);
            })(i);
        }
        setTimeout(done, 200 + cards.length*180 + 600);
        return;
    }
    if (game === 'keno') {
        var drawn = data.drawn || [];
        var picks = data.picks || [];
        var hits = data.hits || [];
        // Animate drawing balls one by one
        var html = '<div class="anim-stage" style="flex-direction:column;gap:10px"><div style="color:#aaa;font-size:0.85em">Drawing 20 numbers...</div><div id="drawnBalls" style="display:flex;flex-wrap:wrap;gap:4px;justify-content:center;max-width:100%"></div></div>';
        ra.innerHTML = html;
        playSound('kenoStart');
        var area = document.getElementById('drawnBalls');
        var i = 0;
        var iv = setInterval(function(){
            if (i >= drawn.length) {
                clearInterval(iv);
                // Highlight hits in keno grid
                var cells = document.querySelectorAll('#kenoGrid .keno-num');
                for (var j = 0; j < cells.length; j++) {
                    var n = parseInt(cells[j].textContent);
                    if (drawn.indexOf(n) >= 0) {
                        cells[j].classList.add(hits.indexOf(n) >= 0 ? 'hit' : 'drawn');
                    }
                }
                setTimeout(done, 400);
                return;
            }
            var n = drawn[i];
            var isHit = picks.indexOf(n) >= 0;
            if (area) {
                var ball = document.createElement('div');
                ball.style.cssText = 'width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.8em;animation:pulse 0.3s ease;'
                    + (isHit ? 'background:#4ade80;color:#fff;box-shadow:0 0 12px #4ade80'
                             : 'background:rgba(255,255,255,0.15);color:#fff');
                ball.textContent = n;
                area.appendChild(ball);
            }
            playSound('keno');
            i++;
        }, 90);
        return;
    }
    done();
}

function showGameResult(data) {
    var ra = document.getElementById('resultArea');
    var isWin = data.result === 'win' || data.result === 'blackjack';
    var cls = isWin ? 'result-win win-glow' : (data.result === 'push' ? 'result-push' : 'result-lose');
    var msg = '';
    if (isWin) { msg = '🎉 WIN! +$' + parseFloat(data.win_amount).toFixed(2); playSound('win'); }
    else if (data.result === 'push') msg = 'PUSH - Bet returned';
    else { msg = '💔 LOSE - $' + parseFloat(data.bet).toFixed(2); playSound('lose'); }
    var extra = buildResultDetails(data);
    var existing = ra.innerHTML || '';
    ra.innerHTML = existing + '<div class="' + cls + '" style="margin-top:8px">' + msg + '</div>' + extra;
    if (data.new_achievements && data.new_achievements.length > 0) {
        var achHtml = '<div style="margin-top:8px;padding:8px;background:rgba(251,191,36,0.2);border-radius:8px">';
        for (var i = 0; i < data.new_achievements.length; i++) {
            var a = data.new_achievements[i];
            achHtml += '<div>' + a.icon + ' <b>' + a.name + '</b> unlocked!</div>';
        }
        achHtml += '</div>';
        ra.innerHTML += achHtml;
    }
    if (currentGame === 'keno' && data.drawn) {
        var cells = document.querySelectorAll('#kenoGrid .keno-num');
        for (var i = 0; i < cells.length; i++) {
            var n = parseInt(cells[i].textContent);
            if (data.drawn.indexOf(n) >= 0) {
                cells[i].classList.add(data.hits && data.hits.indexOf(n) >= 0 ? 'hit' : 'drawn');
            }
        }
    }
}

function buildResultDetails(data) {
    var g = currentGame;
    var html = '<div style="margin-top:8px;font-size:0.85em;color:#aaa">';
    if (g === 'head_tail') html += 'Coin: ' + (data.coin_result || '').toUpperCase();
    else if (g === 'rock_paper_scissors') html += 'Bot chose: ' + (data.bot_choice || '').toUpperCase();
    else if (g === 'spin_wheel') html += 'Landed on: ' + (data.segment_label || '');
    else if (g === 'number_guess') html += 'Secret: ' + data.secret + ' (Diff: ' + data.diff + ')';
    else if (g === 'dice_rolling') html += 'Dice: ' + (data.dice || []).join('+') + ' = ' + data.total;
    else if (g === 'card_finding') html += 'Winning card was position ' + ((data.winning || 0) + 1);
    else if (g === 'number_slot' && data.reels) html += '<div style="font-size:2em">' + data.reels.join(' ') + '</div>';
    else if (g === 'number_pool') html += 'Ball: ' + data.ball;
    else if (g === 'roulette') html += data.number + ' ' + (data.color || '').toUpperCase();
    else if (g === 'casino_dice') html += 'Roll: ' + data.roll + ' | Target: ' + data.target + '%';
    else if (g === 'keno') html += 'Hits: ' + (data.num_hits || 0) + '/' + (data.picks || []).length;
    else if (g === 'color_prediction') html += 'Color: ' + (data.winning_color || '').toUpperCase();
    else if (g === 'crazy_times' || g === 'dream_catcher') html += 'Result: ' + (data.spin_result || '');
    else if (g === 'andar_bahar') html += 'Joker: ' + data.joker + ' | Winner: ' + (data.winner || '').toUpperCase();
    else if (g === 'pai_gow_poker') {
        html += '<div>Your high: ' + (data.player_high||[]).join(' ') + '</div>';
        html += '<div>Dealer high: ' + (data.dealer_high||[]).join(' ') + '</div>';
    }
    if (data.multiplier) html += '<div>Multiplier: ' + data.multiplier + 'x</div>';
    html += '</div>';
    return html;
}

function handleBlackjack(data) {
    var area = document.getElementById('bjArea') || document.getElementById('resultArea');
    if (!area) { showGameResult(data); return; }
    var html = '<div style="margin-bottom:8px"><b style="color:#aaa">Dealer:</b><div class="cards-row">';
    var dealerCards = data.dealer || [];
    for (var i = 0; i < dealerCards.length; i++) {
        var isHidden = dealerCards[i] === '??';
        var isRed = !isHidden && (dealerCards[i].indexOf('♥') >= 0 || dealerCards[i].indexOf('♦') >= 0);
        html += '<div class="card-display' + (isHidden ? ' hidden-card' : (isRed ? ' red' : '')) + '">' + dealerCards[i] + '</div>';
    }
    html += '</div>';
    if (data.dealer_value !== undefined) html += '<div style="color:#aaa;font-size:0.85em">Value: ' + data.dealer_value + '</div>';
    html += '</div>';
    html += '<div style="margin-bottom:8px"><b style="color:#aaa">You:</b><div class="cards-row">';
    var playerCards = data.player || [];
    for (var i = 0; i < playerCards.length; i++) {
        var isRed = playerCards[i].indexOf('♥') >= 0 || playerCards[i].indexOf('♦') >= 0;
        html += '<div class="card-display' + (isRed ? ' red' : '') + '">' + playerCards[i] + '</div>';
    }
    html += '</div>';
    if (data.player_value !== undefined) html += '<div style="color:#aaa;font-size:0.85em">Value: ' + data.player_value + '</div>';
    html += '</div>';
    if (data.done) {
        var cls = data.result === 'win' || data.result === 'blackjack' ? 'result-win' : (data.result === 'push' ? 'result-push' : 'result-lose');
        html += '<div class="' + cls + '" style="margin-top:8px">' + data.result.toUpperCase() + (data.win_amount ? ' +$' + parseFloat(data.win_amount).toFixed(2) : '') + '</div>';
        currentSession = null;
        var pb = document.getElementById('playBtn');
        if (pb) { pb.style.display = ''; pb.disabled = false; pb.textContent = 'Deal Again'; }
    } else {
        currentSession = data.session_id;
        html += '<div class="choice-grid" style="margin-top:8px">';
        html += '<div class="choice-btn" onclick="bjAction(\'hit\')">Hit</div>';
        html += '<div class="choice-btn" onclick="bjAction(\'stand\')">Stand</div>';
        if (data.can_double) html += '<div class="choice-btn" onclick="bjAction(\'double\')">Double</div>';
        html += '</div>';
        var pb = document.getElementById('playBtn');
        if (pb) pb.style.display = 'none';
    }
    area.innerHTML = html;
}

function bjAction(action) {
    playSound('cardflip');
    fetch('/api/casino/play', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game:'blackjack',action:action,session_id:currentSession,bet:0,free_play:isFreePlay})
    }).then(function(r){return r.json()}).then(function(data){
        if (data.error) { showResult(data.error,'lose'); return; }
        updateBalances(data);
        handleBlackjack(data);
    });
}

function handleMinesStart(data) {
    if (data.error) { showResult(data.error, 'lose'); return; }
    currentSession = data.session_id;
    var grid = document.getElementById('minesGrid');
    var html = '';
    for (var i = 0; i < 25; i++) {
        html += '<div class="mine-cell" data-pos="' + i + '" onclick="minesReveal(' + i + ')"></div>';
    }
    grid.innerHTML = html;
    document.getElementById('minesInfo').textContent = 'Gems found: 0 | Tap to reveal';
    document.getElementById('cashoutBtn').style.display = 'none';
    var pb = document.getElementById('playBtn');
    if (pb) pb.style.display = 'none';
}

function minesReveal(pos) {
    if (!currentSession) return;
    fetch('/api/casino/play', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game:'mines',action:'reveal',session_id:currentSession,position:pos,bet:0,free_play:isFreePlay})
    }).then(function(r){return r.json()}).then(function(data){
        if (data.error) { showResult(data.error,'lose'); return; }
        updateBalances(data);
        var cell = document.querySelector('.mine-cell[data-pos="' + pos + '"]');
        if (data.hit_mine) {
            playSound('mine'); playSound('lose');
            if (cell) { cell.textContent = '💣'; cell.classList.add('mine','revealed'); }
            var mines = data.mines || [];
            for (var i = 0; i < mines.length; i++) {
                var c = document.querySelector('.mine-cell[data-pos="' + mines[i] + '"]');
                if (c && !c.classList.contains('mine')) { c.textContent = '💣'; c.classList.add('mine','revealed'); }
            }
            document.getElementById('minesInfo').innerHTML = '<span class="result-lose">BOOM! Lost $' + parseFloat(data.bet).toFixed(2) + '</span>';
            document.getElementById('cashoutBtn').style.display = 'none';
            currentSession = null;
            var pb = document.getElementById('playBtn');
            if (pb) { pb.style.display = ''; pb.disabled = false; pb.textContent = 'Play Again'; }
        } else {
            playSound('click');
            if (cell) { cell.textContent = '💎'; cell.classList.add('gem','revealed'); }
            document.getElementById('minesInfo').textContent = 'Gems: ' + data.gems_found + ' | ' + data.current_multiplier + 'x ($' + parseFloat(data.potential_win).toFixed(2) + ')';
            document.getElementById('cashoutBtn').style.display = '';
        }
    });
}

function minesCashout() {
    if (!currentSession) return;
    playSound('win');
    fetch('/api/casino/play', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game:'mines',action:'cashout',session_id:currentSession,bet:0,free_play:isFreePlay})
    }).then(function(r){return r.json()}).then(function(data){
        if (data.error) { showResult(data.error,'lose'); return; }
        updateBalances(data);
        var mines = data.mines || [];
        for (var i = 0; i < mines.length; i++) {
            var c = document.querySelector('.mine-cell[data-pos="' + mines[i] + '"]');
            if (c) { c.textContent = '💣'; c.classList.add('mine','revealed'); }
        }
        document.getElementById('minesInfo').innerHTML = '<span class="result-win">Cash Out! +$' + parseFloat(data.win_amount).toFixed(2) + ' (' + data.multiplier + 'x)</span>';
        document.getElementById('cashoutBtn').style.display = 'none';
        currentSession = null;
        var pb = document.getElementById('playBtn');
        if (pb) { pb.style.display = ''; pb.disabled = false; pb.textContent = 'Play Again'; }
    });
}

/* ========= CRASH (Aviator-style) ========= */
var crashTimer = null;
var crashStartTs = 0;
var crashGrowth = 0.06;
var crashAutoTarget = null;

function buildCrashUI() {
    var html = '<div style="margin-bottom:10px;display:flex;gap:8px;align-items:center"><label style="color:#aaa;font-size:0.85em">Auto cashout @</label>';
    html += '<input type="number" id="crashAuto" placeholder="2.00" step="0.10" min="1.01" style="width:90px;background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2);color:#fff;padding:6px 8px;border-radius:8px"><span style="color:#aaa;font-size:0.85em">x (optional)</span></div>';
    html += '<div class="crash-stage" id="crashStage">';
    html += '  <div class="crash-stars"></div>';
    html += '  <svg class="crash-curve" id="crashCurve" viewBox="0 0 100 100" preserveAspectRatio="none">';
    html += '    <defs><linearGradient id="crashGrad" x1="0%" y1="100%" x2="100%" y2="0%">';
    html += '      <stop offset="0%" stop-color="#fbbf24" stop-opacity="0.2"/>';
    html += '      <stop offset="50%" stop-color="#f59e0b"/>';
    html += '      <stop offset="100%" stop-color="#ef4444"/>';
    html += '    </linearGradient></defs>';
    html += '    <path class="fill-path" id="crashFill" d="M 8,86 L 8,86 L 8,100 L 8,100 Z"/>';
    html += '    <path id="crashPath" d="M 8,86 L 8,86"/>';
    html += '  </svg>';
    html += '  <div class="crash-mult" id="crashMult">1.00x</div>';
    html += '  <div class="crash-plane" id="crashPlane">&#x2708;&#xFE0F;</div>';
    html += '</div>';
    html += '<button class="play-btn" id="crashCashBtn" style="display:none;background:linear-gradient(135deg,#fbbf24,#f59e0b);margin-top:8px;color:#000;font-weight:800;font-size:1.1em" onclick="crashCashout()">&#x1F4B0; CASH OUT</button>';
    return html;
}

function handleCrashStart(data) {
    if (data.error) { showResult(data.error, 'lose'); return; }
    currentSession = data.session_id;
    /* Server-relative timestamp keeps multiplier in sync */
    var serverNow = data.start_ts || (Date.now()/1000);
    crashStartTs = (Date.now()/1000) - 0.05; /* small offset so first tick > 0 */
    crashGrowth = data.growth_rate || 0.06;
    crashAutoTarget = data.auto_cashout || null;
    var stage = document.getElementById('crashStage');
    if (stage) { stage.classList.remove('crashed-stage'); stage.classList.add('flying'); }
    var plane = document.getElementById('crashPlane');
    if (plane) {
        plane.classList.remove('crashed','escaped');
        plane.innerHTML = '&#x2708;&#xFE0F;';
        plane.style.opacity = '1';
        plane.style.left = '8%'; plane.style.bottom = '14%';
        plane.style.transform = 'rotate(-25deg)';
    }
    var mEl = document.getElementById('crashMult');
    if (mEl) { mEl.textContent = '1.00x'; mEl.style.color = ''; }
    var path = document.getElementById('crashPath');
    var fill = document.getElementById('crashFill');
    if (path) path.setAttribute('d', 'M 8,86 L 8,86');
    if (fill) fill.setAttribute('d', 'M 8,86 L 8,86 L 8,100 L 8,100 Z');
    var pb = document.getElementById('playBtn'); if (pb) pb.style.display='none';
    var cb = document.getElementById('crashCashBtn'); if (cb) { cb.style.display=''; cb.disabled=false; }
    playSound('start');
    if (crashTimer) clearInterval(crashTimer);
    crashTimer = setInterval(crashTick, 60);
}

function crashTick() {
    if (!currentSession) return;
    var now = Date.now()/1000;
    var elapsed = Math.max(0, now - crashStartTs);
    var m = Math.exp(crashGrowth * elapsed);
    var mult = Math.min(m, 100);
    var mEl = document.getElementById('crashMult');
    if (mEl) mEl.textContent = mult.toFixed(2) + 'x';

    /* Plane follows a parabolic curve up-right; progress slows over time */
    var prog = 1 - Math.exp(-elapsed / 8);   /* 0 → 1 (asymptotic) */
    var px = 8 + prog * 78;                  /* 8% → 86%  (x in viewBox) */
    var py = 86 - Math.pow(prog, 0.85) * 70; /* 86 → 16 (y in viewBox; lower = higher) */
    var plane = document.getElementById('crashPlane');
    if (plane) {
        plane.style.left = px + '%';
        plane.style.bottom = (100 - py) + '%';
        /* Rotate based on local slope of the curve */
        var dy = -Math.pow(prog,0.85) * 70 + Math.pow(Math.max(0, prog-0.02), 0.85) * 70;
        var angle = -25 - Math.min(15, prog * 18);
        /* Subtle wobble for "flying" feel */
        var wobble = Math.sin(elapsed * 6) * 1.5;
        plane.style.transform = 'rotate(' + (angle + wobble) + 'deg)';
    }
    /* Build the SVG flight-path curve as the plane moves */
    var path = document.getElementById('crashPath');
    var fill = document.getElementById('crashFill');
    if (path) {
        /* Quadratic bezier from start (8,86) up to current point with control low for arc */
        var d = 'M 8,86 Q ' + (8 + (px-8)*0.55) + ',' + (86 - (86-py)*0.15) + ' ' + px.toFixed(2) + ',' + py.toFixed(2);
        path.setAttribute('d', d);
        if (fill) fill.setAttribute('d', d + ' L ' + px.toFixed(2) + ',100 L 8,100 Z');
    }

    /* Poll server every ~700ms for auto-cashout / crash check */
    if (Math.floor(elapsed * 1000) % 700 < 70) crashPoll();
}

function crashPoll() {
    if (!currentSession) return;
    var sid = currentSession;
    fetch('/api/casino/play', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game:'crash',action:'status',session_id:sid,bet:0,free_play:isFreePlay})
    }).then(function(r){return r.json()}).then(function(data){
        if (!data || data.error) return;
        if (data.done) crashFinish(data);
    }).catch(function(){});
}

function crashCashout() {
    if (!currentSession) return;
    var sid = currentSession;
    var cb = document.getElementById('crashCashBtn'); if (cb) cb.disabled = true;
    playSound('win');
    fetch('/api/casino/play', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game:'crash',action:'cashout',session_id:sid,bet:0,free_play:isFreePlay})
    }).then(function(r){return r.json()}).then(function(data){
        if (data.error) { showResult(data.error,'lose'); if (cb) cb.disabled=false; return; }
        crashFinish(data);
    });
}

function crashFinish(data) {
    if (crashTimer) { clearInterval(crashTimer); crashTimer = null; }
    currentSession = null;
    updateBalances(data);
    var stage = document.getElementById('crashStage');
    var plane = document.getElementById('crashPlane');
    var mEl = document.getElementById('crashMult');
    var cb = document.getElementById('crashCashBtn');
    if (cb) { cb.style.display='none'; cb.disabled=false; }
    if (stage) stage.classList.remove('flying');
    if (data.crashed) {
        if (stage) stage.classList.add('crashed-stage');
        if (plane) { plane.classList.add('crashed'); plane.innerHTML='&#x1F4A5;'; }
        if (mEl) { mEl.textContent = data.crash_point.toFixed(2) + 'x'; mEl.style.color='#ef4444'; }
        playSound('lose');
        showResult('&#x1F4A5; CRASHED at ' + data.crash_point.toFixed(2) + 'x — lost $' + parseFloat(data.bet).toFixed(2), 'lose');
    } else {
        if (mEl) { mEl.textContent = data.multiplier.toFixed(2) + 'x'; mEl.style.color='#4ade80'; }
        if (plane) plane.classList.add('escaped'); /* plane flies off-screen */
        playSound('win');
        var auto = data.auto ? ' (auto)' : '';
        showResult('&#x1F4B0; CASHED OUT @ ' + data.multiplier.toFixed(2) + 'x' + auto + ' — won $' + parseFloat(data.win_amount).toFixed(2), 'win');
    }
    var pb = document.getElementById('playBtn');
    if (pb) { pb.style.display=''; pb.disabled=false; pb.textContent='Play Again'; }
    /* Reset visual state shortly so user can replay cleanly */
    setTimeout(function(){
        if (mEl) mEl.style.color = '';
        if (stage) stage.classList.remove('crashed-stage');
        if (plane) {
            plane.classList.remove('crashed','escaped');
            plane.innerHTML='&#x2708;&#xFE0F;';
            plane.style.left='8%'; plane.style.bottom='14%';
            plane.style.transform='rotate(-25deg)'; plane.style.opacity='1';
        }
        var path = document.getElementById('crashPath');
        var fill = document.getElementById('crashFill');
        if (path) path.setAttribute('d','M 8,86 L 8,86');
        if (fill) fill.setAttribute('d','M 8,86 L 8,86 L 8,100 L 8,100 Z');
    }, 2800);
}

function handlePokerDeal(data) {
    if (data.error) { showResult(data.error, 'lose'); return; }
    var area = document.getElementById('pokerArea') || document.getElementById('resultArea');
    if (data.done) {
        var cls = data.result === 'win' ? 'result-win' : 'result-lose';
        var html = '<div class="cards-row">';
        var hand = data.hand || [];
        for (var i = 0; i < hand.length; i++) {
            var isRed = hand[i].indexOf('♥') >= 0 || hand[i].indexOf('♦') >= 0;
            html += '<div class="card-display' + (isRed ? ' red' : '') + '">' + hand[i] + '</div>';
        }
        html += '</div>';
        html += '<div style="color:#aaa;margin:8px 0">' + (data.hand_name || '') + '</div>';
        html += '<div class="' + cls + '">' + (data.result === 'win' ? 'WIN! +$' + parseFloat(data.win_amount).toFixed(2) + ' (' + data.multiplier + 'x)' : 'No winning hand') + '</div>';
        area.innerHTML = html;
        currentSession = null;
        var pb = document.getElementById('playBtn');
        if (pb) { pb.style.display = ''; pb.disabled = false; pb.textContent = 'Deal Again'; }
    } else {
        currentSession = data.session_id;
        var html = '<div style="color:#aaa;font-size:0.85em;margin-bottom:8px">Click cards to hold, then Draw:</div>';
        html += '<div class="cards-row" id="pokerHand">';
        var hand = data.hand || [];
        for (var i = 0; i < hand.length; i++) {
            var isRed = hand[i].indexOf('♥') >= 0 || hand[i].indexOf('♦') >= 0;
            html += '<div class="card-display' + (isRed ? ' red' : '') + '" data-idx="' + i + '" onclick="toggleHold(this)" style="cursor:pointer">' + hand[i] + '</div>';
        }
        html += '</div>';
        html += '<div style="color:#aaa;margin:8px 0">' + (data.hand_name || '') + '</div>';
        html += '<button class="play-btn" onclick="pokerDraw()" style="margin-top:8px">Draw</button>';
        area.innerHTML = html;
        var pb = document.getElementById('playBtn');
        if (pb) pb.style.display = 'none';
    }
}

function toggleHold(el) {
    playSound('click');
    el.classList.toggle('selected');
    if (el.classList.contains('selected')) {
        el.style.border = '2px solid #8b5cf6';
        el.style.transform = 'translateY(-6px)';
    } else {
        el.style.border = '';
        el.style.transform = '';
    }
}

function pokerDraw() {
    if (!currentSession) return;
    var held = [];
    var cards = document.querySelectorAll('#pokerHand .card-display');
    for (var i = 0; i < cards.length; i++) {
        if (cards[i].classList.contains('selected')) held.push(parseInt(cards[i].getAttribute('data-idx')));
    }
    playSound('cardflip');
    fetch('/api/casino/play', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({game:'poker',action:'draw',session_id:currentSession,hold:held,bet:0,free_play:isFreePlay})
    }).then(function(r){return r.json()}).then(function(data){
        if (data.error) { showResult(data.error,'lose'); return; }
        updateBalances(data);
        handlePokerDeal(data);
    });
}

function updateBalances(data) {
    if (data.balance) document.getElementById('balance').textContent = '$' + data.balance;
    if (data.free_balance) document.getElementById('freeBalance').textContent = '$' + data.free_balance;
}

function showResult(msg, type) {
    var ra = document.getElementById('resultArea');
    if (ra) ra.innerHTML = '<div class="result-' + type + '">' + msg + '</div>';
}

function claimDaily() {
    var btn = document.getElementById('claimBtn');
    btn.disabled = true;
    fetch('/api/casino/daily-claim', {method:'POST'})
    .then(function(r){return r.json()})
    .then(function(data){
        if (data.error) { btn.textContent = data.error; return; }
        updateBalances(data);
        btn.textContent = 'Claimed!';
    })
    .catch(function(){ btn.textContent = 'Error'; });
}

function showPanel(panel) {
    var tabs = document.querySelectorAll('.tab-btn');
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.remove('active');
        if (tabs[i].textContent.toLowerCase().indexOf(panel) >= 0) tabs[i].classList.add('active');
    }
    var area = document.getElementById('panelArea');
    area.innerHTML = '<div style="color:#aaa;text-align:center">Loading...</div>';
    if (panel === 'history') loadHistory();
    else if (panel === 'leaderboard') loadLeaderboard();
    else if (panel === 'achievements') loadAchievements();
}

function loadHistory() {
    fetch('/api/casino/history').then(function(r){return r.json()}).then(function(data){
        var area = document.getElementById('panelArea');
        if (!data || data.length === 0) { area.innerHTML = '<div style="color:#aaa;text-align:center">No bets yet</div>'; return; }
        var html = '<table style="width:100%;border-collapse:collapse;font-size:0.85em"><tr style="color:#aaa"><th>Game</th><th>Bet</th><th>Win</th><th>Result</th><th>Time</th></tr>';
        for (var i = 0; i < data.length; i++) {
            var b = data[i];
            var rc = b.result === 'win' || b.result === 'blackjack' ? '#4ade80' : (b.result === 'push' ? '#f1c40f' : '#ef4444');
            html += '<tr><td>' + b.game + '</td><td>$' + b.bet.toFixed(2) + '</td><td style="color:' + rc + '">$' + b.win.toFixed(2) + '</td><td style="color:' + rc + '">' + b.result.toUpperCase() + '</td><td style="color:#aaa">' + b.time + '</td></tr>';
        }
        html += '</table>';
        area.innerHTML = html;
    });
}

function loadLeaderboard() {
    fetch('/api/casino/leaderboard').then(function(r){return r.json()}).then(function(data){
        var area = document.getElementById('panelArea');
        var lb = data.leaderboard || [];
        if (lb.length === 0) { area.innerHTML = '<div style="color:#aaa;text-align:center">No data yet</div>'; return; }
        var html = '<table style="width:100%;border-collapse:collapse;font-size:0.85em"><tr style="color:#aaa"><th>#</th><th>Player</th><th>Bets</th><th>Won</th><th>Win%</th></tr>';
        for (var i = 0; i < lb.length && i < 20; i++) {
            var e = lb[i];
            var medal = i === 0 ? '&#x1F947;' : (i === 1 ? '&#x1F948;' : (i === 2 ? '&#x1F949;' : ''));
            html += '<tr><td>' + medal + ' ' + e.rank + '</td><td>' + e.username + '</td><td>' + e.total_bets + '</td><td style="color:#4ade80">$' + e.total_won.toFixed(2) + '</td><td>' + e.win_rate + '%</td></tr>';
        }
        html += '</table>';
        area.innerHTML = html;
    });
}

function loadAchievements() {
    fetch('/api/casino/achievements').then(function(r){return r.json()}).then(function(data){
        var area = document.getElementById('panelArea');
        var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px">';
        for (var i = 0; i < data.length; i++) {
            var a = data[i];
            var opacity = a.unlocked ? '1' : '0.4';
            html += '<div style="background:rgba(255,255,255,0.05);padding:10px;border-radius:10px;opacity:' + opacity + '">';
            html += '<div style="font-size:1.5em">' + a.icon + '</div><div style="font-weight:600;color:#fff">' + a.name + '</div>';
            html += '<div style="font-size:0.75em;color:#aaa">' + a.description + '</div>';
            if (a.unlocked_at) html += '<div style="font-size:0.7em;color:#8b5cf6">' + a.unlocked_at + '</div>';
            html += '</div>';
        }
        html += '</div>';
        area.innerHTML = html;
    });
}

showPanel('history');
</script>
</body></html>'''


ADMIN_CASINO_HTML = r'''<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Casino Admin</title>
<style>
{{ admin_css }}
.admin-wrap { padding: 16px; max-width: 100%; margin: 0 auto; width: 100%; box-sizing: border-box; }
.admin-wrap, .admin-wrap * { box-sizing: border-box; }
.admin-wrap > * { max-width: 100%; }
.msg { background: rgba(139,92,246,0.2); border: 1px solid rgba(139,92,246,0.3); padding: 12px 16px;
    border-radius: 10px; margin-bottom: 16px; color: #e2e8f0; }
.section { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 18px; margin-bottom: 18px; }
.section h3 { color: #fff; margin: 0 0 14px 0; font-size: 1.1em; }
.table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%; }
table { width: 100%; border-collapse: collapse; min-width: 420px; }
.rewards-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }
.rewards-col { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; padding: 12px; min-width: 0; }
.rewards-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 8px; }
.rwd-cell { display: flex; flex-direction: column; min-width: 0; }
.rwd-cell label { color: #888; font-size: 0.7em; margin-bottom: 3px; text-transform: uppercase; letter-spacing: 0.3px; }
.rwd-cell input[type=number] { width: 100%; padding: 8px 10px; }
.field-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
.field { display: flex; flex-direction: column; min-width: 0; flex: 1 1 130px; }
.field label { color: #b3b3c6; font-size: 0.7em; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.3px; font-weight: 600; }
.field input[type=number], .field input[type=text] { width: 100%; }
th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 0.85em; vertical-align: middle; }
th { color: #b3b3c6; font-weight: 600; text-transform: uppercase; font-size: 0.72em; letter-spacing: 0.4px; }
tr:hover td { background: rgba(255,255,255,0.02); }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
.stat-box { background: linear-gradient(135deg, rgba(139,92,246,0.15), rgba(236,72,153,0.15));
    padding: 14px 16px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.06); }
.stat-box .label { font-size: 0.7em; color: #b3b3c6; text-transform: uppercase; letter-spacing: 0.4px; font-weight: 600; }
.stat-box .value { font-size: 1.3em; font-weight: 700; color: #fff; margin-top: 4px; }
input[type=number], input[type=text], select { background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.18); color: #fff; padding: 9px 12px; border-radius: 8px;
    font-size: 0.88em; outline: none; transition: border-color 0.15s; }
input[type=number]:focus, input[type=text]:focus, select:focus { border-color: #8b5cf6; }
.btn { padding: 9px 18px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;
    font-size: 0.85em; color: #fff; transition: all 0.15s; white-space: nowrap;
    display: inline-flex; align-items: center; justify-content: center; min-height: 36px; }
.btn:hover { transform: translateY(-1px); }
.btn-purple { background: linear-gradient(135deg, #8b5cf6, #7c3aed); box-shadow: 0 2px 8px rgba(139,92,246,0.3); }
.btn-green { background: #4ade80; color: #0f1a2e; }
.btn-red { background: #ef4444; }
.btn-yellow { background: #f59e0b; color: #1a1a2e; }
.inline-form { display: inline; }
.toggle-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.form-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.form-row input, .form-row select { min-width: 0; }
.action-form { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; padding: 12px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
    flex: 1 1 280px; min-width: 0; }
.action-form input[type=number] { width: 110px; flex-shrink: 0; }
.action-form select { flex: 1; min-width: 140px; max-width: 100%; }
.action-form button { flex-shrink: 0; }
@media(max-width:600px) {
    .section { padding: 14px; }
    .action-form { flex: 1 1 100%; }
    .action-form select { width: 100%; flex-basis: 100%; }
    .btn { padding: 9px 14px; font-size: 0.82em; }
}
</style>
</head><body>
<div class="admin-wrap">
<a href="/admin" style="color:#8b5cf6;text-decoration:none;font-size:0.85em">&larr; Back to Admin</a>
<h2 style="color:#fff;margin:12px 0 16px">Casino Admin Panel</h2>

{% if message %}<div class="msg">{{ message }}</div>{% endif %}

<div class="stat-grid">
    <div class="stat-box"><div class="label">Total Bets</div><div class="value">{{ stats.total_bets }}</div></div>
    <div class="stat-box"><div class="label">Total Wagered</div><div class="value">${{ "%.2f"|format(stats.total_wagered) }}</div></div>
    <div class="stat-box"><div class="label">Total Paid</div><div class="value">${{ "%.2f"|format(stats.total_paid) }}</div></div>
    <div class="stat-box"><div class="label">House Profit</div><div class="value" style="color:{{ '#4ade80' if stats.house_profit >= 0 else '#ef4444' }}">${{ "%.2f"|format(stats.house_profit) }}</div></div>
    <div class="stat-box"><div class="label">Free Bets</div><div class="value">{{ stats.free_bets }}</div></div>
</div>

<div class="section">
    <h3>Casino Status</h3>
    <div class="toggle-row">
        <span style="color:#fff">Casino is <b style="color:{{ '#4ade80' if casino_on else '#ef4444' }}">{{ 'ON' if casino_on else 'OFF' }}</b></span>
        <form method="POST" class="inline-form">
            <input type="hidden" name="action" value="toggle_casino">
            <button type="submit" class="btn {{ 'btn-red' if casino_on else 'btn-green' }}">{{ 'Disable' if casino_on else 'Enable' }}</button>
        </form>
    </div>
</div>

<div class="section">
    <h3>Game Settings (19 Games)</h3>
    <form method="POST">
        <input type="hidden" name="action" value="save_edges">
        <div class="table-wrap"><table>
            <tr><th>Game</th><th>House Edge %</th><th>Win Prob</th><th>Status</th><th>Action</th></tr>
            {{ games_html|safe }}
        </table></div>
        <button type="submit" class="btn btn-purple" style="margin-top:12px">Save All Edges</button>
    </form>
</div>

<div class="section">
    <h3>Bet Limits</h3>
    <form method="POST">
        <input type="hidden" name="action" value="save_limits">
        <div class="field-row">
            <div class="field"><label>Min Bet</label>
                <input type="number" name="min_bet" value="{{ min_bet }}" step="0.01" min="0.01"></div>
            <div class="field"><label>Max Bet</label>
                <input type="number" name="max_bet" value="{{ max_bet }}" step="1" min="1"></div>
            <button type="submit" class="btn btn-purple">Save</button>
        </div>
    </form>
</div>

<div class="section">
    <h3>Daily Free Play</h3>
    <div class="toggle-row">
        <span style="color:#fff">Daily free is <b style="color:{{ '#4ade80' if daily_enabled else '#ef4444' }}">{{ 'ON' if daily_enabled else 'OFF' }}</b></span>
        <form method="POST" class="inline-form">
            <input type="hidden" name="action" value="toggle_daily">
            <button type="submit" class="btn {{ 'btn-red' if daily_enabled else 'btn-green' }}">{{ 'Disable' if daily_enabled else 'Enable' }}</button>
        </form>
    </div>
    <form method="POST">
        <input type="hidden" name="action" value="save_daily">
        <div class="field-row">
            <div class="field"><label>Daily Amount</label>
                <input type="number" name="daily_amount" value="{{ daily_amount }}" step="0.5"></div>
            <div class="field"><label>Max Win</label>
                <input type="number" name="daily_max_win" value="{{ daily_max }}" step="1"></div>
            <button type="submit" class="btn btn-purple">Save</button>
        </div>
    </form>
</div>

<div class="section">
    <h3>Leaderboard Rewards</h3>
    <div class="toggle-row">
        <span style="color:#fff">Rewards: <b style="color:{{ '#4ade80' if lb_config.enabled else '#ef4444' }}">{{ 'ON' if lb_config.enabled else 'OFF' }}</b></span>
        <form method="POST" class="inline-form">
            <input type="hidden" name="action" value="toggle_lb_rewards">
            <button type="submit" class="btn {{ 'btn-red' if lb_config.enabled else 'btn-green' }}">Toggle</button>
        </form>
        <span style="color:#fff;margin-left:16px">Auto: <b style="color:{{ '#4ade80' if lb_config.auto_payout else '#ef4444' }}">{{ 'ON' if lb_config.auto_payout else 'OFF' }}</b></span>
        <form method="POST" class="inline-form">
            <input type="hidden" name="action" value="toggle_auto_payout">
            <button type="submit" class="btn {{ 'btn-red' if lb_config.auto_payout else 'btn-green' }}">Toggle</button>
        </form>
    </div>
    <form method="POST">
        <input type="hidden" name="action" value="save_lb_rewards">
        <div class="rewards-grid">
            <div class="rewards-col">
                <b style="color:#b3b3c6;font-size:0.78em;text-transform:uppercase;letter-spacing:0.4px">Weekly Rewards</b>
                <div class="rewards-row">
                    <div class="rwd-cell"><label>1st</label><input type="number" name="weekly_1st" value="{{ lb_config.weekly[1] }}" step="1"></div>
                    <div class="rwd-cell"><label>2nd</label><input type="number" name="weekly_2nd" value="{{ lb_config.weekly[2] }}" step="1"></div>
                    <div class="rwd-cell"><label>3rd</label><input type="number" name="weekly_3rd" value="{{ lb_config.weekly[3] }}" step="1"></div>
                </div>
            </div>
            <div class="rewards-col">
                <b style="color:#b3b3c6;font-size:0.78em;text-transform:uppercase;letter-spacing:0.4px">Monthly Rewards</b>
                <div class="rewards-row">
                    <div class="rwd-cell"><label>1st</label><input type="number" name="monthly_1st" value="{{ lb_config.monthly[1] }}" step="1"></div>
                    <div class="rwd-cell"><label>2nd</label><input type="number" name="monthly_2nd" value="{{ lb_config.monthly[2] }}" step="1"></div>
                    <div class="rwd-cell"><label>3rd</label><input type="number" name="monthly_3rd" value="{{ lb_config.monthly[3] }}" step="1"></div>
                </div>
            </div>
        </div>
        <button type="submit" class="btn btn-purple" style="margin-top:12px">Save Rewards</button>
    </form>
    <div style="margin-top:12px;display:flex;gap:8px">
        <form method="POST" class="inline-form">
            <input type="hidden" name="action" value="payout_rewards">
            <input type="hidden" name="payout_period" value="weekly">
            <button type="submit" class="btn btn-yellow">Pay Weekly</button>
        </form>
        <form method="POST" class="inline-form">
            <input type="hidden" name="action" value="payout_rewards">
            <input type="hidden" name="payout_period" value="monthly">
            <button type="submit" class="btn btn-yellow">Pay Monthly</button>
        </form>
    </div>
    {% if reward_html %}
    <div style="margin-top:12px">
        <b style="color:#aaa;font-size:0.85em">Recent Payouts</b>
        <div class="table-wrap"><table><tr><th>Rank</th><th>User</th><th>Period</th><th>Amount</th><th>Paid</th></tr>
        {{ reward_html|safe }}</table></div>
    </div>
    {% endif %}
</div>

<div class="section" style="background:linear-gradient(135deg,rgba(74,222,128,0.08),rgba(139,92,246,0.06));border-color:rgba(74,222,128,0.2)">
    <h3 style="color:#4ade80">💰 Load Funds to User</h3>
    <p style="color:#b3b3c6;font-size:0.82em;margin:0 0 12px 0">Add or deduct shop balance for any user. Use a negative amount to deduct.</p>
    <form method="POST">
        <input type="hidden" name="action" value="load_funds">
        <div class="field-row">
            <div class="field"><label>User ID</label>
                <input type="number" name="fund_user_id" placeholder="e.g. 1857417752" value="{{ lookup_user_id }}" required></div>
            <div class="field"><label>Amount ($)</label>
                <input type="number" name="fund_amount" step="0.01" placeholder="10.00" required></div>
            <div class="field" style="flex:2 1 200px"><label>Note (optional)</label>
                <input type="text" name="fund_note" placeholder="Reason for credit..."></div>
            <button type="submit" class="btn btn-green" onclick="return confirm('Confirm fund load?')">Load Funds</button>
        </div>
    </form>
</div>

<div class="section">
    <h3>Achievements Management</h3>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        <form method="GET" class="action-form">
            <input type="number" name="lookup_user" placeholder="User ID" value="{{ lookup_user_id }}">
            <button type="submit" class="btn btn-purple">Lookup</button>
        </form>
        <form method="POST" class="action-form">
            <input type="hidden" name="action" value="grant_achievement">
            <input type="hidden" name="lookup_user_preserve" value="{{ lookup_user_id }}">
            <input type="number" name="user_id" placeholder="User ID" value="{{ lookup_user_id }}">
            <select name="achievement_id">
                {% for aid, adef in achievement_defs.items() %}
                <option value="{{ aid }}">{{ adef.icon }} {{ adef.name }}</option>
                {% endfor %}
            </select>
            <button type="submit" class="btn btn-green">Grant</button>
        </form>
        <form method="POST" class="action-form">
            <input type="hidden" name="action" value="revoke_achievement">
            <input type="hidden" name="lookup_user_preserve" value="{{ lookup_user_id }}">
            <input type="number" name="user_id" placeholder="User ID" value="{{ lookup_user_id }}">
            <select name="achievement_id">
                {% for aid, adef in achievement_defs.items() %}
                <option value="{{ aid }}">{{ adef.icon }} {{ adef.name }}</option>
                {% endfor %}
            </select>
            <button type="submit" class="btn btn-red">Revoke</button>
        </form>
    </div>
    {{ lookup_html|safe }}
    {% if ach_html %}
    <div class="table-wrap"><table><tr><th>Achievement</th><th>Unlocks</th><th>Description</th></tr>
    {{ ach_html|safe }}</table></div>
    {% endif %}
</div>

<div class="section">
    <h3>Recent Bets</h3>
    {% if recent_html %}
    <div class="table-wrap"><table><tr><th>User</th><th>Game</th><th>Bet</th><th>Win</th><th>Result</th><th>Type</th><th>Time</th></tr>
    {{ recent_html|safe }}</table></div>
    {% else %}
    <p style="color:#aaa">No bets yet.</p>
    {% endif %}
</div>

<div class="section">
    <h3>Exports</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
        <a href="/admin/casino/export/bets" class="btn btn-purple" style="text-decoration:none">Export Bets CSV</a>
        <a href="/admin/casino/export/achievements" class="btn btn-purple" style="text-decoration:none">Export Achievements CSV</a>
    </div>
</div>
</div>
</body></html>'''
