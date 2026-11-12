import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';

// StrictMode는 쓰지 않음: 개발 중 효과가 두 번 실행되면 캡처 스트림이 두 번 열릴 수 있음
createRoot(document.getElementById('root')!).render(<App />);
