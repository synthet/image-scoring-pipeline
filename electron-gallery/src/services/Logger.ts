export class Logger {
    static info(message: string, data?: any) {
        this.log('INFO', message, data);
    }

    static error(message: string, data?: any) {
        this.log('ERROR', message, data);
    }

    static debug(message: string, data?: any) {
        this.log('DEBUG', message, data);
    }

    static warn(message: string, data?: any) {
        this.log('WARN', message, data);
    }

    private static log(level: string, message: string, data?: any) {
        // Log to console for dev
        if (level === 'ERROR') console.error(message, data);
        else if (level === 'WARN') console.warn(message, data);
        else console.log(`[${level}] ${message}`, data);

        // Send to Electron backend
        if (window.electron && window.electron.log) {
            window.electron.log(level, message, data).catch(err => {
                console.error('Failed to send log to backend', err);
            });
        }
    }
}
