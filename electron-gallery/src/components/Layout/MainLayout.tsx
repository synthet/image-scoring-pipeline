import React from 'react';
import '../../styles/layout.css';

interface MainLayoutProps {
    sidebar: React.ReactNode;
    content: React.ReactNode;
    header?: React.ReactNode;
}

export const MainLayout: React.FC<MainLayoutProps> = ({ sidebar, content, header }) => {
    return (
        <div className="app-container">
            <aside className="sidebar">
                {sidebar}
            </aside>
            <main className="main-content">
                <header className="top-bar">
                    {header || <span>Image Gallery</span>}
                </header>
                <div className="content-area">
                    {content}
                </div>
            </main>
        </div>
    );
};
