// Old/static servers and HTTP errors may return HTML rather than the API contract.
export async function readAPIJSON(response){
  const text=await response.text();
  try{return JSON.parse(text);}
  catch{
    const endpoint=(()=>{try{return new URL(response.url).pathname;}catch{return 'the API';}})();
    if(/^\s*</.test(text))throw Error(`The coaching server returned a web page for ${endpoint} (HTTP ${response.status}). Open Ori on port 8766 and refresh. If this continues, restart the coaching server.`);
    throw Error(`The coaching server returned an invalid response (HTTP ${response.status}). Please try again.`);
  }
}
