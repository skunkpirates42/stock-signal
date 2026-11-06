import ScopeNote from "@/components/ScopeNote";
import Page from "@/components/Page";
import Button from "@/components/Button";

export default function SavedResultNotFound() {
  return (
    <Page>
      <h1>Saved result not found</h1>
      <ScopeNote>This saved result doesn’t exist or can’t be opened here.</ScopeNote>
      <Button href="/research">Back to saved research</Button>
    </Page>
  );
}
