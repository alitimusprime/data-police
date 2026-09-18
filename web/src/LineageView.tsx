import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ArrowDownRight, ArrowUpRight, Database, GitBranch, Layers3, X } from 'lucide-react';
import { api, dateTime } from './api';
import { Badge, Button, Heading, Health, State } from './components';
import { useWorkspace } from './App';
import type { Dataset } from './types';

type AssetNode = Node<{ asset: Dataset; dimmed: boolean; selected: boolean }>;
function AssetCard({ data }: NodeProps<AssetNode>) {
  return (
    <div
      className={
        'graph-node ' +
        data.asset.status +
        (data.dimmed ? ' dimmed' : '') +
        (data.selected ? ' selected' : '')
      }
    >
      <Handle type="target" position={Position.Left} />
      <div className="graph-node-top">
        <Database size={15} />
        <span>{data.asset.layer}</span>
        <span className={'node-health-dot ' + data.asset.status} />
      </div>
      <strong>{data.asset.name}</strong>
      <div className="graph-node-bottom">
        <span>{data.asset.health == null ? 'Not measured' : data.asset.health + ' / 100'}</span>
        <span>{data.asset.status}</span>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { asset: AssetCard };

export function LineageView({ focus }: { focus?: string }) {
  const { go } = useWorkspace(),
    [selected, setSelected] = useState(focus || ''),
    [direction, setDirection] = useState<'downstream' | 'upstream'>('downstream');
  const query = useQuery({
    queryKey: ['lineage'],
    queryFn: () => api<{ nodes: Dataset[]; edges: { source: string; target: string }[] }>('/lineage'),
    refetchInterval: 15000,
  });
  const paths = useMemo(() => {
    const found = new Set<string>(selected ? [selected] : []),
      queue = selected ? [selected] : [];
    while (queue.length) {
      const node = queue.shift()!;
      for (const edge of query.data?.edges || []) {
        const from = direction === 'downstream' ? edge.source : edge.target,
          to = direction === 'downstream' ? edge.target : edge.source;
        if (from === node && !found.has(to)) {
          found.add(to);
          queue.push(to);
        }
      }
    }
    return found;
  }, [selected, direction, query.data]);
  const nodes = useMemo(() => {
    const layers = ['raw', 'reference', 'staging', 'curated', 'analytics'],
      positioned: AssetNode[] = [];
    for (const layer of layers) {
      const assets = (query.data?.nodes || []).filter((n) => n.layer === layer);
      const column = layer === 'reference' ? 0 : layers.indexOf(layer) - 1;
      assets.forEach((asset, index) =>
        positioned.push({
          id: asset.id,
          type: 'asset',
          position: { x: Math.max(0, column) * 310, y: index * 160 + (layer === 'reference' ? 820 : 0) },
          data: { asset, dimmed: !!selected && !paths.has(asset.id), selected: selected === asset.id },
        }),
      );
    }
    return positioned;
  }, [query.data, selected, paths]);
  const edges = useMemo(
    () =>
      (query.data?.edges || []).map((e) => ({
        id: e.source + '-' + e.target,
        ...e,
        type: 'smoothstep',
        animated: !!selected && paths.has(e.source) && paths.has(e.target),
        style: {
          stroke: paths.has(e.source) && paths.has(e.target) ? '#36a58a' : '#c8d4d0',
          strokeWidth: paths.has(e.source) && paths.has(e.target) ? 2.3 : 1.2,
          opacity: selected && !(paths.has(e.source) && paths.has(e.target)) ? 0.22 : 1,
        },
      })),
    [query.data, paths, selected],
  );
  const clickNode = useCallback((_: React.MouseEvent, node: Node) => setSelected(node.id), []);
  if (!query.data) return <State error={query.error} />;
  const asset = query.data.nodes.find((n) => n.id === selected);
  return (
    <>
      <Heading
        eyebrow="FOLLOW THE DEPENDENCIES"
        title="Lineage explorer"
        description="Trace the path from raw sources to business-facing datasets."
      >
        <div className="segmented">
          <button
            className={direction === 'upstream' ? 'active' : ''}
            onClick={() => setDirection('upstream')}
          >
            <ArrowUpRight size={15} />
            Upstream
          </button>
          <button
            className={direction === 'downstream' ? 'active' : ''}
            onClick={() => setDirection('downstream')}
          >
            <ArrowDownRight size={15} />
            Downstream
          </button>
        </div>
      </Heading>
      <div className="graph-toolbar">
        <span>
          <Layers3 size={15} />
          {query.data.nodes.length} assets <span className="sep">/</span> {edges.length} dependencies
        </span>
        <div className="graph-legend">
          <span>
            <i className="healthy" />
            Healthy
          </span>
          <span>
            <i className="critical" />
            Critical
          </span>
          <span>
            <i className="unknown" />
            Unknown
          </span>
        </div>
        {selected && (
          <button className="text-button" onClick={() => setSelected('')}>
            Clear selection <X size={14} />
          </button>
        )}
      </div>
      <div className="graph-workspace">
        <div className="graph-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={clickNode}
            fitView
            fitViewOptions={{
              nodes: selected ? [...paths].map((id) => ({ id })) : undefined,
              padding: 0.2,
              maxZoom: 1,
              minZoom: 0.3,
            }}
            minZoom={0.22}
            maxZoom={1.5}
            nodesDraggable={false}
            nodesConnectable={false}
            deleteKeyCode={null}
            proOptions={{ hideAttribution: false }}
          >
            <Background color="#d8e2df" gap={20} size={1} />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(n) => {
                const a = (n.data as { asset: Dataset }).asset;
                return a.status === 'healthy' ? '#4fac95' : a.status === 'critical' ? '#d77474' : '#bbc9c5';
              }}
              maskColor="rgba(247,250,248,.65)"
            />
          </ReactFlow>
        </div>
        {asset ? (
          <aside className="graph-inspector">
            <div className="panel-heading">
              <h2>Asset details</h2>
              <button
                className="icon-button"
                aria-label="Clear selected asset"
                onClick={() => setSelected('')}
              >
                <X size={16} />
              </button>
            </div>
            <div className="inspector-content">
              <span className="inspector-icon">
                <Database size={23} />
              </span>
              <h3>{asset.name}</h3>
              <Badge status={asset.status} />
              <p>{asset.description}</p>
              <dl className="detail-list">
                <div>
                  <dt>Health</dt>
                  <dd>
                    <Health value={asset.health} />
                  </dd>
                </div>
                <div>
                  <dt>Owner</dt>
                  <dd>{asset.owner}</dd>
                </div>
                <div>
                  <dt>Layer</dt>
                  <dd>{asset.layer}</dd>
                </div>
                <div>
                  <dt>Latest materialization</dt>
                  <dd>{dateTime(asset.last_materialized)}</dd>
                </div>
              </dl>
              <div className="impact-counter">
                <strong>{paths.size - 1}</strong>
                <span>
                  {direction} assets
                  <br />
                  reachable through lineage
                </span>
              </div>
              <p className="microcopy">Reachability indicates potential impact, not confirmed failure.</p>
              <Button primary onClick={() => go('datasets/' + asset.id)}>
                Inspect dataset <ArrowUpRight size={15} />
              </Button>
            </div>
          </aside>
        ) : (
          <div className="graph-hint">
            <GitBranch size={16} />
            Select an asset to trace its dependencies.
          </div>
        )}
      </div>
    </>
  );
}
