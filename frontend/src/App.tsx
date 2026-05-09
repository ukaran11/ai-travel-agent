import { ChatInterface } from "./components/ChatInterface";
import { ErrorBoundary } from "./components/ErrorBoundary";

function App() {
    return (
        <ErrorBoundary>
            <ChatInterface />
        </ErrorBoundary>
    );
}

export default App;
