import ScopeNote from "@/components/ScopeNote";
import Page from "@/components/Page";
import Button from "@/components/Button";

export default function RunNotFound() {
  return (
    <Page>
      <h1>Run not found</h1>
      <ScopeNote>This run doesn’t exist or can’t be opened here.</ScopeNote>
      <Button href="/runs">Back to run history</Button>
    </Page>
  );
}
