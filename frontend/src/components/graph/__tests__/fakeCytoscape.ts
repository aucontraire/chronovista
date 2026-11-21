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
  addClass: (c: string) => void;
  removeClass: (c: string) => void;
  hasClass: (c: string) => boolean;
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
  /** Sets what `cy.pan()` / `cy.zoom()` report (the user's current view). */
  setViewport: (v: { pan: { x: number; y: number }; zoom: number }) => void;
  /** Fires registered handlers for an event on an element, e.g. `emit("dbltap", "node-id")`. */
  emit: (event: string, id?: string) => void;
  /** Ids of elements currently carrying a class (e.g. "filtered"). */
  withClass: (cls: string) => string[];
}

export const fake = {
  instances: [] as FakeCy[],
  layoutCalls: [] as Record<string, unknown>[],
  /** Ordered "resize" / "layout" calls, to assert what ran before a layout. */
  events: [] as string[],
  /** How many times a running layout was stopped. */
  layoutStops: 0,
  reset() {
    fake.instances.length = 0;
    fake.layoutCalls.length = 0;
    fake.events.length = 0;
    fake.layoutStops = 0;
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
    return {
      run: () => {
        fake.layoutCalls.push(opts);
        fake.events.push("layout");
      },
      stop: () => void fake.layoutStops++,
    };
  }
}

const factory = vi.fn(() => {
  const store = new Map<string, { def: FakeDef; el: FakeEl }>();
  const positions = new Map<string, { x: number; y: number }>();
  type Handler = (evt: { target: { data: (k: string) => unknown; renderedPosition: () => { x: number; y: number } } }) => void;
  const handlers = new Map<string, Handler[]>();
  const view = { pan: { x: 0, y: 0 }, zoom: 1 };
  const all = (group?: string) =>
    new Coll(
      [...store.values()].filter((e) => !group || e.def.group === group).map((e) => e.el),
      store,
    );
  const cy: FakeCy & Record<string, unknown> = {
    added: [],
    destroy: vi.fn(),
    resize: vi.fn(() => void fake.events.push("resize")),
    fit: vi.fn(),
    // Getter form (no argument) reports the viewport; the setter form is only recorded.
    zoom: vi.fn((z?: number) => (z === undefined ? view.zoom : undefined)),
    pan: vi.fn((p?: { x: number; y: number }) => (p === undefined ? view.pan : undefined)),
    add(defs: FakeDef[]) {
      for (const def of defs) {
        const id = String(def.data["id"]);
        const el: FakeEl = {
          id: () => id,
          classes: def.classes ?? "",
          position: () => positions.get(id) ?? { x: 0, y: 0 },
          addClass: (c) => {
            if (!el.hasClass(c)) el.classes = `${el.classes} ${c}`.trim();
          },
          removeClass: (c) => {
            el.classes = el.classes.split(" ").filter((x) => x !== c).join(" ");
          },
          hasClass: (c) => el.classes.split(" ").includes(c),
        };
        store.set(id, { def, el });
        cy.added.push(def);
      }
    },
    elements: () => all(),
    edges: () => all("edges"),
    nodes: () => all("nodes"),
    // cy.on(events, selector, fn) or cy.on(events, fn); "a b" registers both events.
    on(events: string, a: unknown, b?: unknown) {
      const fn = (typeof a === "function" ? a : b) as Handler;
      for (const event of events.split(" ")) handlers.set(event, [...(handlers.get(event) ?? []), fn]);
    },
    setPosition: (id, pos) => void positions.set(id, pos),
    setViewport: (v) => void Object.assign(view, v),
    emit(event, id) {
      const def = id ? store.get(id)?.def : undefined;
      for (const fn of handlers.get(event) ?? []) {
        fn({
          target: {
            data: (k: string) => def?.data[k],
            renderedPosition: () => (id ? positions.get(id) : undefined) ?? { x: 0, y: 0 },
          },
        });
      }
    },
    withClass: (cls) => [...store.values()].filter((e) => e.el.hasClass(cls)).map((e) => e.el.id()),
  };
  fake.instances.push(cy);
  return cy;
});
(factory as unknown as { use: () => void }).use = () => undefined;

export const fakeCytoscapeModule = { default: factory };
