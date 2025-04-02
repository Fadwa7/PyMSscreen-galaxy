import { createContext, useContext, useState, useEffect } from 'react';

const AppStateContext = createContext();

export function AppStateProvider({ children }) {
  const savedState = sessionStorage.getItem('appState');

  const [appState, setAppState] = useState(
    savedState
      ? JSON.parse(savedState)
      : {
          working_directory: '',
          compound_csv: '',
          mzml_files: []
        }
  );

  const updateAppState = (updates) => {
    setAppState(prev => ({ ...prev, ...updates }));
  };

  useEffect(() => {
    sessionStorage.setItem('appState', JSON.stringify(appState));
  }, [appState]);

  return (
    <AppStateContext.Provider value={{ appState, updateAppState }}>
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState() {
  return useContext(AppStateContext);
}
