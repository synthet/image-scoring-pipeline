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
  const [currentImageIndex, setCurrentImageIndex] = useState<number>(0);

  const { images, loadMore } = useImages(50, selectedFolderId, filters);

  const handleSelectFolder = (folder: Folder) => {
    setSelectedFolderId(folder.id);
  };

  const handleImageClick = (image: any) => {
    const index = images.findIndex(img => img.id === image.id);
    setCurrentImageIndex(index >= 0 ? index : 0);
    setOpeningImage(image);
  };

  const handleNavigateImage = (newIndex: number) => {
    if (newIndex >= 0 && newIndex < images.length) {
      setCurrentImageIndex(newIndex);
      setOpeningImage(images[newIndex]);
    }
  };

  const handleNavigateToParent = () => {
    if (!selectedFolderId) return;

    // Find parent of current folder
    const findParent = (nodes: Folder[], targetId: number, parentId?: number): number | undefined => {
      for (const node of nodes) {
        if (node.id === targetId) return parentId;
        if (node.children) {
          const result = findParent(node.children, targetId, node.id);
          if (result !== undefined) return result;
        }
      }
      return undefined;
    };

    const parentId = findParent(folders, selectedFolderId);
    setSelectedFolderId(parentId);
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
            onNavigateToParent={handleNavigateToParent}
            viewerOpen={!!openingImage}
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
            })}
            onSelectFolder={handleSelectFolder}
          />
          {openingImage && (
            <ImageViewer
              image={openingImage}
              onClose={closeViewer}
              allImages={images}
              currentIndex={currentImageIndex}
              onNavigate={handleNavigateImage}
            />
          )}
        </div>
      }
    />
  );
}

export default App;
