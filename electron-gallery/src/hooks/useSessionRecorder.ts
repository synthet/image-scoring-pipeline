import { useEffect } from 'react';
import { Logger } from '../services/Logger';

export function useSessionRecorder() {
    useEffect(() => {
        const handleEvent = (e: Event) => {
            const target = e.target as HTMLElement;
            let targetDesc = target.tagName;
            if (target.id) targetDesc += `#${target.id}`;
            if (target.className && typeof target.className === 'string') targetDesc += `.${target.className.split(' ').join('.')}`;
            if (target.innerText && target.innerText.length < 20) targetDesc += `("${target.innerText}")`;

            // Filter out noisy events or frequent ones if needed
            // For scroll, we might throttle or just log start/end? 
            // Logging every scroll event is too much.
            if (e.type === 'scroll') return;

            Logger.info('Interaction', {
                type: e.type,
                target: targetDesc,
                x: (e as MouseEvent).clientX,
                y: (e as MouseEvent).clientY,
                key: (e as KeyboardEvent).key
            });
        };


        window.addEventListener('click', handleEvent, true);
        window.addEventListener('keydown', handleEvent, true);

        // Log errors
        const handleError = (event: ErrorEvent) => {
            Logger.error('Uncaught Exception', { message: event.message, filename: event.filename, lineno: event.lineno });
        };
        const handleRejection = (event: PromiseRejectionEvent) => {
            Logger.error('Unhandled Rejection', { reason: event.reason });
        };

        window.addEventListener('error', handleError);
        window.addEventListener('unhandledrejection', handleRejection);

        Logger.info('Session Recorder attached');

        return () => {
            window.removeEventListener('click', handleEvent, true);
            window.removeEventListener('keydown', handleEvent, true);
            window.removeEventListener('error', handleError);
            window.removeEventListener('unhandledrejection', handleRejection);
        };
    }, []);
}
