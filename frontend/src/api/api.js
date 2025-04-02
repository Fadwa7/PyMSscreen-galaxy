import axios from 'axios';

const API_BASE = 'http://localhost:5000';

export const saveState = (state) => {
  return axios.post(`${API_BASE}/save_state`, state);
};

export const loadState = (payload) => {
  return axios.post(`${API_BASE}/load_state`, payload);
};

export const generateTable = (payload) => {
  return axios.post(`${API_BASE}/generate_table`, payload, {
    headers: {
      'Content-Type': 'application/json',
    }
  });
};

export const saveExtractConfig = async (config) => {
  return axios.post('http://localhost:5000/save_extract_config', config);
};

export const extractData = (payload) => {
  return axios.post(`http://localhost:5000/extract_data`, payload, {
    headers: {
      'Content-Type': 'application/json',
    }
  });
};

export const prescreenData = (payload) => {
  return axios.post('http://localhost:5000/prescreen_data', payload, {
    headers: {
      'Content-Type': 'application/json',
    }
  });
};

export const loadComprehensiveTable = async (workingDirectory) => {
  return axios.get('http://localhost:5000/load_comprehensive_table', {
    params: { working_directory: workingDirectory }
  });
};

export const exportSummaryPDF = async (compounds, working_directory) => {
  // Properly structure payload for backend
  const payload = {
    working_directory,
    compound_groups: compounds.reduce((groups, compound) => {
      const group = groups.find(g => g.group_name === compound.ID);
      if (group) {
        group.compounds.push(compound);
      } else {
        groups.push({
          group_name: compound.ID,
          compounds: [compound]
        });
      }
      return groups;
    }, [])
  };

  try {
    const response = await axios.post('http://localhost:5000/export_summary_pdf', payload, {
      responseType: 'blob'
    });
    return response.data;
  } catch (error) {
    console.error('PDF export failed:', error);
    throw new Error('PDF export failed');
  }
};
