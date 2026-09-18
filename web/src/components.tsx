import { ReactNode } from 'react';
import {
  AlertCircle,
  ArrowUpRight,
  Check,
  ChevronRight,
  Database,
  LoaderCircle,
  ShieldCheck,
  X,
} from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import ReactECharts from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart as ELineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';
import { clock, formatNumber, human } from './api';
import type { Dataset, Incident } from './types';

echarts.use([ELineChart, GridComponent, TooltipComponent, CanvasRenderer]);

export function Badge({ status }: { status: string }) {
  return (
    <span className={'badge ' + status}>
      <span />
      {human(status)}
    </span>
  );
}
export function Logo() {
  return (
    <span className="brand-mark">
      <ShieldCheck size={24} strokeWidth={1.7} />
    </span>
  );
}
export function Button({
  children,
  onClick,
  primary = false,
  disabled = false,
  className = '',
  type = 'button',
}: {
  children: ReactNode;
  onClick?: () => void;
  primary?: boolean;
  disabled?: boolean;
  className?: string;
  type?: 'submit' | 'button';
}) {
  return (
    <button
      type={type}
      className={`btn ${primary ? 'primary' : ''} ${className}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
export function State({
  error,
  empty,
  title,
  children,
}: {
  error?: Error | null;
  empty?: boolean;
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className={'state ' + (error ? 'error-state' : '')}>
      {error ? (
        <AlertCircle size={27} />
      ) : empty ? (
        <Database size={28} />
      ) : (
        <LoaderCircle className="spin" size={27} />
      )}
      <h3>
        {error ? 'Unable to load this view' : title || (empty ? 'Nothing here yet' : 'Loading workspace')}
      </h3>
      <p>{error?.message || children}</p>
      {error && <Button onClick={() => location.reload()}>Try again</Button>}
    </div>
  );
}
export function Heading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
export function Panel({
  title,
  meta,
  children,
  className = '',
}: {
  title?: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={'panel ' + className}>
      {title && (
        <div className="panel-heading">
          <h2>{title}</h2>
          {meta}
        </div>
      )}
      {children}
    </section>
  );
}
export function Metric({
  label,
  value,
  caption,
  icon,
}: {
  label: string;
  value: ReactNode;
  caption: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {label}
        {icon}
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-caption">{caption}</div>
    </div>
  );
}
export function Health({ value }: { value: number | null }) {
  return (
    <div className="health-cell">
      <div className="mini-track">
        <span
          style={{
            width: `${value || 0}%`,
            background:
              value === null ? '#b0babc' : value >= 90 ? '#288c77' : value >= 60 ? '#c18d25' : '#cf6262',
          }}
        />
      </div>
      <strong>{value === null ? 'N/A' : formatNumber(value)}</strong>
    </div>
  );
}
export function DatasetTable({ datasets, onOpen }: { datasets: Dataset[]; onOpen: (id: string) => void }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Status</th>
            <th>Health</th>
            <th>Layer</th>
            <th>Owner</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {datasets.map((d) => (
            <tr key={d.id} onClick={() => onOpen(d.id)} className="clickable">
              <td>
                <button
                  className="cell-link"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpen(d.id);
                  }}
                >
                  <span className="dataset-symbol">
                    <Database size={16} />
                  </span>
                  <span className="mono">{d.name}</span>
                </button>
              </td>
              <td>
                <Badge status={d.status} />
              </td>
              <td>
                <Health value={d.health} />
              </td>
              <td>
                <span className={'layer ' + d.layer}>{d.layer}</span>
              </td>
              <td className="muted">{d.owner}</td>
              <td>
                <ChevronRight size={15} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!datasets.length && (
        <State empty title="No matching datasets">
          Try a different search or layer.
        </State>
      )}
    </div>
  );
}
export function IncidentRows({ incidents, onOpen }: { incidents: Incident[]; onOpen: (id: number) => void }) {
  return (
    <div className="incident-list">
      {incidents.length ? (
        incidents.map((i) => (
          <button key={i.id} className="incident-row" onClick={() => onOpen(i.id)}>
            <span className={'incident-symbol ' + i.severity}>
              <AlertCircle size={19} />
            </span>
            <span className="incident-copy">
              <span className="incident-title">{i.title}</span>
              <span className="meta">
                DP-{i.id + 1000}
                <span className="sep">/</span>
                {i.root_dataset_id}
              </span>
            </span>
            <Badge status={i.status} />
            <ArrowUpRight size={17} />
          </button>
        ))
      ) : (
        <div className="quiet-success">
          <Check size={22} />
          <div>
            <strong>No active incidents</strong>
            <p>All clear. New findings will appear here.</p>
          </div>
        </div>
      )}
    </div>
  );
}
export function LineChart({
  data,
  series,
  label = 'Health',
  color = '#258b75',
  height = 250,
  max,
}: {
  data: { at: string; [key: string]: unknown }[];
  series: string;
  label?: string;
  color?: string;
  height?: number;
  max?: number;
}) {
  const option: EChartsOption = {
    animationDuration: 400,
    grid: { left: 47, right: 25, top: 20, bottom: 32 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#10292b',
      borderWidth: 0,
      textStyle: { color: '#fff' },
      confine: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: data.map((d) => clock(d.at)),
      axisLine: { lineStyle: { color: '#e1e7e6' } },
      axisTick: { show: false },
      axisLabel: { color: '#80908d', fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      max,
      min: 0,
      splitNumber: 4,
      axisLabel: { color: '#80908d', fontSize: 11 },
      splitLine: { lineStyle: { color: '#edf1ef', type: 'dashed' } },
    },
    series: [
      {
        name: label,
        data: data.map((d) => Number(d[series])),
        type: 'line',
        smooth: 0.25,
        symbolSize: 5,
        showSymbol: data.length < 3,
        lineStyle: { width: 2.5, color },
        itemStyle: { color },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: color + '22' },
              { offset: 1, color: color + '00' },
            ],
          },
        },
      },
    ],
  };
  return data.length ? (
    <ReactECharts echarts={echarts} option={option} style={{ height }} notMerge />
  ) : (
    <div className="chart-empty">Historical measurements will appear after ingestion.</div>
  );
}
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content className="modal">
          <div className="modal-header">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close className="icon-button" aria-label="Close">
              <X size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Description>{description}</Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
