export default function PagePlaceholder({ title, phase }: { title: string; phase: string }) {
  return (
    <section className="page-placeholder">
      <h2>{title}</h2>
      <p>This page is scaffolded in Phase 1. Real content arrives in {phase}.</p>
    </section>
  );
}
