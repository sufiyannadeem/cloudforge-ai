import ProjectWorkspace from "@/components/workspaces/ProjectWorkspace";
export default async function DriftPage({ searchParams }: { searchParams: Promise<{ project?: string; offset?: string }> }) {
  const query = await searchParams;
  return <ProjectWorkspace mode="drift" requested={query.project} offset={query.offset} />;
}
