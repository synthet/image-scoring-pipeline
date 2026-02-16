# Sidebars and Navigation

## FilterPanel
`src/components/Sidebar/FilterPanel.tsx`
A controlled component for applying filters to the image gallery.
- **Filters**:
  - **Minimum Rating**: 0 to 5 stars.
  - **Color Label**: Red, Yellow, Green, Blue, Purple (or All).
- **Props**: `filters` object and `onChange` callback.

## FolderTree
`src/components/Tree/FolderTree.tsx`
A recursive tree component for navigating the file system structure stored in the database.
- **Features**:
  - Expand/Collapse folders.
  - Highlight current selection.
  - Recursively renders `TreeNode` components.
- **Utils**: `src/components/Tree/treeUtils.ts` converts the flat database records (with `parent_id`) into a nested `Folder` object structure.
