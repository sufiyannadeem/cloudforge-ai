import ProjectWorkspace from "@/components/workspaces/ProjectWorkspace";
export default async function AgentPage({ searchParams }: { searchParams: Promise<{ project?: string; offset?: string }> }) {
  const query = await searchParams;
  return <ProjectWorkspace mode="agent" requested={query.project} offset={query.offset} />;
}
