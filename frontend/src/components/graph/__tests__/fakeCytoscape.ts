/**
 * A recording stand-in for the lazily imported `cytoscape` module (jsdom cannot rasterise a
 * canvas). It implements only what `ConnectionGraph` calls. Use it from a test with:
 *
 *   vi.mock("cytoscape-fcose", () => ({ default: {} }));
 *   vi.mock("cytoscape", async () => (await import("./fakeCytoscape")).fakeCytoscapeModule);
 */

import { vi } from "vitest";

export interface FakeDef {
  group: string;
  data: Record<string, unknown>;
  classes?: string;
}

interface FakeEl {
  id: () => string;
  classes: string;
  position: () => { x: number; y: number };
}

export interface FakeCy {
  added: FakeDef[];
  destroy: ReturnType<typeof vi.fn>;
  resize: ReturnType<typeof vi.fn>;
  fit: ReturnType<typeof vi.fn>;
  zoom: ReturnType<typeof vi.fn>;
  pan: ReturnType<typeof vi.fn>;
  /** Simulates a layout having placed a node. */
  setPosition: (id: string, pos: { x: number; y: number }) => void;
  /** Fires registered handlers, e.g. `emit("dbltap", "node-id")`. */
  emit: (event: string, id: string) => void;
}

export const fake = {
  instances: [] as FakeCy[],
  layoutCalls: [] as Record<string, unknown>[],
  reset() {
    fake.instances.length = 0;
    fake.layoutCalls.length = 0;
  },
};

class Coll {
  constructor(
    readonly items: FakeEl[],
    private readonly store: Map<string, unknown>,
  ) {}
  get length() {
    return this.items.length;
  }
  forEach(fn: (e: FakeEl) => void) {
    this.items.forEach(fn);
  }
  filter(fn: (e: FakeEl) => boolean) {
    return new Coll(this.items.filter(fn), this.store);
  }
  map<T>(fn: (e: FakeEl) => T) {
    return this.items.map(fn);
  }
  toArray() {
    return this.items;
  }
  remove() {
    this.items.forEach((e) => this.store.delete(e.id()));
  }
  not(sel: string) {
    const cls = sel.replace(".", "");
    return new Coll(
      this.items.filter((e) => !e.classes.split(" ").includes(cls)),
      this.store,
    );
  }
  layout(opts: Record<string, unknown>) {
    return { run: () => void fake.layoutCalls.push(opts), stop: () => undefined };
  }
}

const factory = vi.fn(() => {
  const store = new Map<string, { def: FakeDef; el: FakeEl }>();
  const positions = new Map<string, { x: number; y: number }>();
  const handlers = new Map<string, ((evt: { target: { data: (k: string) => unknown } }) => void)[]>();
  const all = (group?: string) =>
    new Coll(
      [...store.values()].filter((e) => !group || e.def.group === group).map((e) => e.el),
      store,
    );
  const cy: FakeCy & Record<string, unknown> = {
    added: [],
    destroy: vi.fn(),
    resize: vi.fn(),
    fit: vi.fn(),
    zoom: vi.fn(),
    pan: vi.fn(),
    add(defs: FakeDef[]) {
      for (const def of defs) {
        const id = String(def.data["id"]);
        const el: FakeEl = {
          id: () => id,
          classes: def.classes ?? "",
          position: () => positions.get(id) ?? { x: 0, y: 0 },
        };
        store.set(id, { def, el });
        cy.added.push(def);
      }
    },
    elements: () => all(),
    edges: () => all("edges"),
    nodes: () => all("nodes"),
    on(event: string, _selector: string, fn: (evt: { target: { data: (k: string) => unknown } }) => void) {
      handlers.set(event, [...(handlers.get(event) ?? []), fn]);
    },
    setPosition: (id, pos) => void positions.set(id, pos),
    emit(event, id) {
      const def = store.get(id)?.def;
      for (const fn of handlers.get(event) ?? []) {
        fn({ target: { data: (k: string) => def?.data[k] } });
      }
    },
  };
  fake.instances.push(cy);
  return cy;
});
(factory as unknown as { use: () => void }).use = () => undefined;

export const fakeCytoscapeModule = { default: factory };
