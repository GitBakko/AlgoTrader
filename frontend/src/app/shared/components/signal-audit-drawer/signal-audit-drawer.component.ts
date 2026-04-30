import {
  Component,
  ChangeDetectionStrategy,
  DestroyRef,
  HostListener,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { SignalAuditService } from '../../../core/services/signal-audit.service';
import { TradingService } from '../../../core/services/trading.service';
import { EpicLogoComponent } from '../epic-logo/epic-logo.component';
import { SpinnerComponent } from '@coreui/angular';
import { SlCooldownInfo, PaperPosition, PositionEvent } from '../../../core/models';
import { WebSocketService } from '../../../core/services/websocket.service';

type AuditDrawerTab = 'audit' | 'history';
type OutcomeBadge = 'going' | 'tp' | 'sl' | 'manual' | 'unreconciled' | 'none';

@Component({
  selector: 'app-signal-audit-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, EpicLogoComponent, SpinnerComponent],
  templateUrl: './signal-audit-drawer.component.html',
  styleUrls: ['./signal-audit-drawer.component.scss'],
})
export class SignalAuditDrawerComponent {
  readonly auditService = inject(SignalAuditService);
  private readonly trading = inject(TradingService);
  private readonly ws = inject(WebSocketService);
  private readonly destroyRef = inject(DestroyRef);

  /** Tabbed view mirrors PositionDetailDrawer for EXECUTED signals.
   *  REJECTED signals (no position) skip tabs and show the audit body
   *  directly — tabs would be misleading without a position to overview
   *  or a history timeline. */
  readonly activeTab = signal<AuditDrawerTab>('audit');
  readonly hasTabs = computed<boolean>(() => {
    const audit = this.auditService.currentAudit();
    return !!(audit && audit.status === 'EXECUTED' && audit.deal_id);
  });

  /** Outcome badge for the header strip.
   *  - going: position currently open at broker
   *  - tp: closed at take-profit (or close_reason='TP')
   *  - sl: closed at stop-loss (or close_reason='SL')
   *  - manual: closed by user/admin
   *  - unreconciled: close detected but P&L could not be reconciled
   *  - none: signal rejected or no position info
   */
  readonly outcomeBadge = computed<OutcomeBadge>(() => {
    const audit = this.auditService.currentAudit();
    if (!audit) return 'none';
    if (audit.status !== 'EXECUTED') return 'none';
    // Authoritative source: positions.status from backend audit response.
    // Falls back to events / livePosition only when the backend did not
    // populate position_status (legacy audits, missing positions row).
    const posStatus = audit.position_status;
    if (posStatus === 'CLOSED') {
      const reason = (audit.close_reason || '').toUpperCase();
      if (reason === 'TP') return 'tp';
      if (reason === 'SL') return 'sl';
      if (reason === 'MANUAL') return 'manual';
      if (reason === 'UNRECONCILED') return 'unreconciled';
      // Fall back to realised P&L sign when close_reason is missing.
      const pl = audit.position_profit_loss;
      if (pl != null) return pl >= 0 ? 'tp' : 'sl';
      return 'unreconciled';
    }
    if (posStatus === 'OPEN') return 'going';

    // Legacy fallback (no position_status from backend): use livePosition
    // matched by deal_id. Avoid epic-only matching — that falsely flags
    // closed audits as GOING when a newer position on the same epic is
    // currently open.
    if (this.livePosition()) return 'going';
    const ev = this.events();
    if (ev) {
      const close = ev.find((e) => e.type === 'CLOSE');
      const reason = (close?.close_reason || '').toUpperCase();
      if (reason === 'TP') return 'tp';
      if (reason === 'SL') return 'sl';
      if (reason === 'MANUAL') return 'manual';
      if (reason === 'UNRECONCILED') return 'unreconciled';
      if (close?.profit_loss != null) {
        return close.profit_loss >= 0 ? 'tp' : 'sl';
      }
    }
    return 'unreconciled';
  });

  outcomeBadgeLabel(badge: OutcomeBadge): string {
    switch (badge) {
      case 'going': return 'GOING';
      case 'tp': return 'TP';
      case 'sl': return 'SL';
      case 'manual': return 'MANUAL';
      case 'unreconciled': return 'UNRECONCILED';
      default: return '';
    }
  }

  readonly events = signal<PositionEvent[] | null>(null);
  readonly eventsLoading = signal<boolean>(false);
  readonly eventsError = signal<string | null>(null);
  /** Track which deal we're fetching for so a stale in-flight response
   *  cannot overwrite the new deal's events when the drawer is reused. */
  private inflightDealId: string | null = null;
  /** The deal we last reset state for, so opening the same drawer twice
   *  doesn't drop a successful fetch. */
  private lastSeenDealId: string | null = null;

  /** Reactively respond to the audit changing — pure read, no signal
   *  writes inside the effect (writes inside effects can cycle when the
   *  written signal is also tracked elsewhere). The actual state mutations
   *  happen in the synchronous helper called below from a microtask. */
  private readonly _auditChangeEffect = effect(() => {
    const audit = this.auditService.currentAudit();
    const dealId = audit?.deal_id ?? null;
    const status = audit?.status ?? null;
    // Defer mutations out of the reactive context.
    queueMicrotask(() => this._onAuditChanged(dealId, status));
  });

  private _onAuditChanged(
    dealId: string | null,
    status: string | null,
  ): void {
    if (dealId === this.lastSeenDealId) return;
    this.lastSeenDealId = dealId;
    // Reset events buffer for the new deal.
    this.events.set(null);
    this.eventsError.set(null);
    this.inflightDealId = null;
    // Default tab is always 'audit' (overview was redundant — its content
    // duplicated info already visible in the header + audit cards).
    this.activeTab.set('audit');
  }

  // Live position for THIS audit's deal_id (matches by deal_id, not epic
  // — multiple positions on the same epic over time would otherwise all
  // resolve to the currently-open one and falsely badge closed audits as
  // GOING).
  readonly livePosition = computed<PaperPosition | null>(() => {
    const audit = this.auditService.currentAudit();
    const dealId = audit?.deal_id ?? null;
    if (!dealId) return null;
    return this.trading.paperPositions().find(p => p.deal_id === dealId) ?? null;
  });

  // Live P&L for open position
  readonly livePnl = computed<number | null>(() => {
    const pos = this.livePosition();
    if (!pos) return null;
    const tick = this.ws.prices()[pos.epic];
    if (!tick) return null;
    const current = pos.direction === 'BUY' ? tick.bid : tick.offer;
    const diff = pos.direction === 'BUY'
      ? current - pos.level
      : pos.level - current;
    return Math.round(diff * pos.size * 100) / 100;
  });

  // Get SL cooldown for the current audit's epic from the latest signal data
  readonly epicCooldown = computed<SlCooldownInfo | null>(() => {
    const epic = this.auditService.currentAudit()?.epic;
    if (!epic) return null;
    // Find the most recent signal for this epic that has cooldown info
    const signals = this.trading.paperSignals();
    for (const sig of signals) {
      if (sig.epic === epic && sig.sl_cooldown) return sig.sl_cooldown;
    }
    return null;
  });

  setTab(tab: AuditDrawerTab): void {
    this.activeTab.set(tab);
    // Trigger a fetch only when transitioning into history AND we have not
    // already fetched (or just-finished fetching) for this deal. Caller-
    // driven instead of effect-driven to avoid signal-write loops.
    if (tab !== 'history') return;
    const dealId = this.auditService.currentAudit()?.deal_id;
    if (!dealId) return;
    if (this.inflightDealId === dealId) return; // already fetching
    if (this.events() !== null) return; // already have data; user can Riprova for fresh
    this.fetchEvents(dealId);
  }

  retryFetchEvents(): void {
    const dealId = this.auditService.currentAudit()?.deal_id;
    if (!dealId) return;
    this.fetchEvents(dealId);
  }

  private fetchEvents(dealId: string): void {
    this.inflightDealId = dealId;
    this.eventsLoading.set(true);
    this.eventsError.set(null);
    this.trading
      .fetchPositionEvents(dealId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (data) => {
          if (this.inflightDealId !== dealId) return;
          this.events.set(this._dedupeEvents(data?.events ?? []));
          this.eventsLoading.set(false);
        },
        error: () => {
          if (this.inflightDealId !== dealId) return;
          this.eventsError.set('Caricamento eventi fallito');
          this.eventsLoading.set(false);
        },
      });
  }

  /** Defensive dedupe: when both v1 and v2 close detectors persist a CLOSE
   *  Trade row for the same deal (or when reconciler ticks twice with the
   *  same disappeared position), the API surfaces both. The duplicate row
   *  often carries the entry price as a fallback when the broker exit
   *  price was unknown. Keep the row whose price moves furthest from the
   *  position's entry price (= the real fill); drop the other.
   */
  private _dedupeEvents(events: PositionEvent[]): PositionEvent[] {
    const audit = this.auditService.currentAudit();
    const entry = audit?.entry_price ?? null;
    const closes = events.filter((e) => e.type === 'CLOSE');
    if (closes.length <= 1) return events;
    let keep: PositionEvent | null = null;
    if (entry != null) {
      // Real exit price diverges from entry; entry-fallback CLOSE rows match
      // entry exactly, so prefer the row whose price is furthest from entry.
      let bestDist = -Infinity;
      for (const c of closes) {
        const p = c.price;
        if (p == null) continue;
        const d = Math.abs(p - entry);
        if (d > bestDist) {
          bestDist = d;
          keep = c;
        }
      }
    }
    // Fallback when no entry context: prefer the latest non-null-price row.
    if (!keep) {
      keep = closes.find((c) => c.price != null) ?? closes[0];
    }
    return events.filter((e) => e.type !== 'CLOSE' || e === keep);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.auditService.isOpen()) {
      this.auditService.close();
    }
  }

  onBackdropClick(): void {
    this.auditService.close();
  }

  voteEntries(): [string, any][] {
    const votes = this.auditService.currentAudit()?.features?.votes;
    if (!votes) return [];
    return Object.entries(votes);
  }

  gateEntries(): [string, any][] {
    const gates = this.auditService.currentAudit()?.features?.gates;
    if (!gates) return [];
    return Object.entries(gates);
  }

  gatesPassed(): number {
    return this.gateEntries().filter(([, g]) => g?.passed === true).length;
  }

  gatesTotal(): number {
    return this.gateEntries().filter(([, g]) => g !== null).length;
  }

  voteLabel(key: string): string {
    const labels: Record<string, string> = {
      // ScalpScore votes
      ema: 'EMA', rsi: 'RSI', macd: 'MACD',
      volume: 'Volume', adx: 'ADX', bb_keltner: 'BB/Keltner',
      sentiment: 'Sentiment',
      // MeanReversion votes
      z_score: 'Z-Score', vwap_z: 'VWAP Z', bb_pctb: 'BB %B',
    };
    return labels[key] ?? key.toUpperCase();
  }

  gateLabel(key: string): string {
    const labels: Record<string, string> = {
      // ScalpScore gates
      session: 'Sessione', dead_market: 'Mercato Morto',
      vwap: 'VWAP', htf: 'HTF Trend', confluence: 'Confluenza',
      data_quality: 'Data Quality',
      // MeanReversion gates
      trending_filter: 'Filtro Trend',
      z_threshold: 'Soglia Z',
      quality_gate: 'Quality Gate',
      ml_agreement: 'ML Agreement',
    };
    return labels[key] ?? key;
  }

  mlAgreementColor(): string {
    const ml = this.auditService.currentAudit()?.features?.ml;
    if (!ml) return 'secondary';
    switch (ml.agreement) {
      case 'agree': return 'success';
      case 'neutral': return 'warning';
      case 'disagree': return 'danger';
      default: return 'secondary';
    }
  }

  mlAgreementLabel(): string {
    const ml = this.auditService.currentAudit()?.features?.ml;
    if (!ml) return '';
    switch (ml.agreement) {
      case 'agree': return 'Concorda';
      case 'neutral': return 'Neutrale';
      case 'disagree': return 'Disaccordo';
      default: return ml.agreement;
    }
  }

  snapshotEntries(): [string, any][] {
    const snapshot = this.auditService.currentAudit()?.features?.market_snapshot;
    if (!snapshot) return [];
    return Object.entries(snapshot);
  }

  snapshotLabel(key: string): string {
    const labels: Record<string, string> = {
      price: 'Prezzo', atr: 'ATR', rsi: 'RSI', adx: 'ADX',
      vwap: 'VWAP', htf_bias: 'HTF Bias', volume: 'Volume',
      bb_width: 'BB Width',
      vwap_z: 'VWAP Z',
      bb_pctb: 'BB %B',
      sentiment_composite: 'Sentiment',
    };
    return labels[key] ?? key;
  }

  formatValue(val: any): string {
    if (val === null || val === undefined) return '-';
    if (typeof val === 'number') return val.toFixed(4);
    return String(val);
  }

  /** Confidence tone tier — mirrors heatmap/feed thresholds so the same
   *  signal color shows up consistently across the cockpit. */
  confidenceTone(conf: number | null | undefined): 'high' | 'mid' | 'low' | 'none' {
    if (conf === null || conf === undefined) return 'none';
    const pct = conf * 100;
    if (pct >= 50) return 'high';
    if (pct >= 30) return 'mid';
    if (pct > 0) return 'low';
    return 'none';
  }

  /** Map a vote weight (-1, 0, +1) to a fill percentage of the bar half.
   *  Each side of the bar represents 100%, so a +1 vote = 100% right fill,
   *  a 0 vote = 0%. Built so the layout extends naturally to ±2 votes if
   *  an indicator group ever returns stronger weights. */
  voteFillPct(value: number | null | undefined): number {
    if (value === null || value === undefined) return 0;
    return Math.min(100, Math.abs(value) * 100);
  }

  /** "BUY 4 · SELL 2" header used in the votes card for a quick scan. */
  voteSummary(): string {
    const entries = this.voteEntries();
    if (entries.length === 0) return '';
    let buy = 0;
    let sell = 0;
    for (const [, v] of entries) {
      const value = v?.value ?? 0;
      if (value > 0) buy += value;
      else if (value < 0) sell += Math.abs(value);
    }
    return `· BUY ${buy} / SELL ${sell}`;
  }

  /** Compact one-liner summary to display on the right of a gate row. */
  gateDetail(key: string, gate: any): string {
    if (!gate) return '';
    if (gate.reason) return String(gate.reason);
    switch (key) {
      // ScalpScore gates
      case 'session':
        return `mult ${(gate.session_mult ?? 0).toFixed(1)} · ${gate.zone ?? ''}`.trim();
      case 'dead_market':
        return `ADX ${gate.adx?.toFixed?.(1) ?? gate.adx ?? '—'}`;
      case 'vwap':
        return gate.bias ? `bias ${gate.bias}` : '';
      case 'htf':
        return gate.htf_bias ? `bias ${gate.htf_bias}` : '';
      case 'confluence':
        return `${gate.buy_count ?? 0}/${gate.effective_min ?? 0} BUY · ${gate.sell_count ?? 0} SELL`;
      case 'data_quality':
        return gate.passed === false ? 'missing data' : 'OK';
      // MeanReversion gates
      case 'trending_filter':
        return `ADX ${gate.adx?.toFixed?.(1) ?? '—'} / max ${gate.adx_max ?? '—'}`;
      case 'z_threshold': {
        const z = gate.z;
        const entry = gate.z_entry;
        return `|z| ${(Math.abs(Number(z) || 0)).toFixed(2)} / ${entry}`;
      }
      case 'quality_gate':
        return `min ${gate.min_quality ?? '—'}`;
      case 'ml_agreement':
        return `ML ${gate.ml_direction ?? '—'} · MR ${gate.mr_direction ?? '—'}`;
      default:
        return '';
    }
  }

  /** Pipeline-stage state used in the header chain (passed/failed/neutral).
   *  Drives the dot color so the user sees at a glance which stage tripped
   *  the rejection. */
  stageState(stage: 'strategy' | 'ml' | 'risk' | 'outcome'): 'passed' | 'failed' | 'neutral' {
    const audit = this.auditService.currentAudit();
    if (!audit) return 'neutral';
    const features = audit.features || {};
    if (stage === 'outcome') {
      return audit.status === 'EXECUTED' ? 'passed' : audit.status === 'REJECTED' ? 'failed' : 'neutral';
    }
    if (stage === 'strategy') {
      const gates = features.gates;
      if (!gates) return 'neutral';
      const allPass = Object.values(gates).every(
        (g: any) => g === null || g === undefined || g.passed !== false,
      );
      return allPass ? 'passed' : 'failed';
    }
    if (stage === 'ml') {
      const ml = features.ml;
      if (!ml) return 'neutral';
      if (ml.agreement === 'agree') return 'passed';
      if (ml.agreement === 'disagree') return 'failed';
      return 'neutral';
    }
    if (stage === 'risk') {
      const risk = features.risk;
      if (!risk) return 'neutral';
      const cb = risk.circuit_breakers?.passed;
      const dd = risk.drawdown?.passed;
      if (cb === false || dd === false) return 'failed';
      if (cb === true && dd === true) return 'passed';
      return 'neutral';
    }
    return 'neutral';
  }
}
