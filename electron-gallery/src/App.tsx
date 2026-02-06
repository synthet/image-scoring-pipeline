import { useState } from 'react';
import { MainLayout } from './components/Layout/MainLayout';
import { useDatabase, useImageCount, useImages } from './hooks/useDatabase';
import { useFolders } from './hooks/useFolders';
import { FolderTree } from './components/Tree/FolderTree';
import type { Folder } from './components/Tree/treeUtils';
import { GalleryGrid } from './components/Gallery/GalleryGrid';
import { FilterPanel } from './components/Sidebar/FilterPanel';
import type { FilterState } from './components/Sidebar/FilterPanel';
import { ImageViewer } from './components/Viewer/ImageViewer';
import { useSessionRecorder } from './hooks/useSessionRecorder';

function App() {
  useSessionRecorder();
  const { isConnected, error } = useDatabase();
  const { count, loading: countLoading } = useImageCount();
  const { folders, loading: foldersLoading } = useFolders();

  const [selectedFolderId, setSelectedFolderId] = useState<number | undefined>(undefined);
  const [filters, setFilters] = useState<FilterState>({ minRating: 0 });
  const [openingImage, setOpeningImage] = useState<any | null>(null);

  const { images, loadMore } = useImages(50, selectedFolderId, filters);

  const handleSelectFolder = (folder: Folder) => {
    setSelectedFolderId(folder.id);
  };

  const handleImageClick = (image: any) => {
    setOpeningImage(image);
  };

  const closeViewer = () => {
    setOpeningImage(null);
  };

  if (!isConnected && !error) return <div style={{ padding: 20 }}>Connecting to services...</div>;
  if (error) return <div style={{ padding: 20, color: 'red' }}>Error: {error}</div>;

  return (
    <MainLayout
      sidebar={
        <div style={{ padding: 10, display: 'flex', flexDirection: 'column', height: '100%' }}>
          <h3 style={{ marginBottom: 10 }}>Folders</h3>
          <div style={{ marginBottom: 10, fontSize: '0.8em', color: '#888' }}>
            <p>Total Images: {countLoading ? '...' : count}</p>
            <p>DB Status: Connected</p>
          </div>

          <FilterPanel filters={filters} onChange={setFilters} />

          <div style={{ flex: 1, overflow: 'hidden', borderTop: '1px solid #333', paddingTop: 10 }}>
            {foldersLoading ? <div>Loading folders...</div> : (
              <FolderTree folders={folders} onSelect={handleSelectFolder} selectedId={selectedFolderId} />
            )}
          </div>
        </div>
      }
      content={
        <div style={{ height: '100%', overflow: 'hidden' }}>
          <GalleryGrid
            images={images}
            onSelect={handleImageClick}
            onEndReached={loadMore}
            subfolders={folders.flatMap(f => {
              const find = (nodes: Folder[]): Folder | undefined => {
                for (const node of nodes) {
                  if (node.id === selectedFolderId) return node;
                  if (node.children) {
                    const found = find(node.children);
                    if (found) return found;
                  }
                }
              };
              return find([f])?.children || [];
            })} // Removed [0] as flatMap already returns the flattened array of children
            onSelectFolder={handleSelectFolder}
          />
          {openingImage && (
            <ImageViewer image={openingImage} onClose={closeViewer} />
          )}
        </div>
      }
    />
  );
}

export default App
