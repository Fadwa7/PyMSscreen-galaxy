import Plotly from 'plotly.js-dist-min';

export async function exportCombinedPlot({ plots, smilesUrl, filename }) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');

  const width = 1000;
  const plotHeight = 600;
  const smilesHeight = 200;
  const totalHeight = plotHeight * plots.length + smilesHeight;

  canvas.width = width;
  canvas.height = totalHeight;

  // White background
  ctx.fillStyle = 'white';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const loadImageFromUrl = (url) => new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.src = url;
  });

  const renderAndCapturePlot = async (data, layout) => {
    const tempDiv = document.createElement('div');
    tempDiv.style.position = 'absolute';
    tempDiv.style.top = '-10000px';
    tempDiv.style.left = '-10000px';
    tempDiv.style.width = `${width}px`;
    tempDiv.style.height = `${plotHeight}px`;
    document.body.appendChild(tempDiv);

    await Plotly.newPlot(tempDiv, data, layout, {
      staticPlot: true,
      responsive: false,
      displayModeBar: false
    });

    // Small delay to ensure canvas layers are painted (important for bar charts)
    await new Promise(resolve => setTimeout(resolve, 300));

    const imageData = await Plotly.toImage(tempDiv, {
      format: 'png',
      width,
      height: plotHeight,
      scale: 1
    });

    document.body.removeChild(tempDiv);
    return imageData;
  };

  for (let i = 0; i < plots.length; i++) {
    const { data, layout } = plots[i];
    const image64 = await renderAndCapturePlot(data, layout);
    if (!image64) continue;

    const img = await loadImageFromUrl(image64);
    ctx.drawImage(img, 0, i * plotHeight, width, plotHeight);
  }

  if (smilesUrl) {
    const img = await loadImageFromUrl(smilesUrl);
    ctx.drawImage(img, width - 200, totalHeight - smilesHeight + 10, 180, 180);
  }

  const link = document.createElement('a');
  link.download = `${filename}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
}
