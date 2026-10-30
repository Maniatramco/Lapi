"use client";
import './page-template.css';

type Intro={group:string;step?:string;title:string;text:string};
/** Purpose lines for workspace screens. Dashboard, Lapi Agent and Add knowledge have their own heroes. */
export const PAGE_INTROS:Record<string,Intro>={
 'Datasets':{group:'Onboard',step:'Step 1 of 4',title:'Collections',text:'Create collections, map their models and upload documents. Each collection keeps its own access and knowledge.'},
 'Prompt templates':{group:'Onboard',step:'Step 2 of 4',title:'Prompts',text:'Save extraction templates that define which fields to pull from documents.'},
 'Extract Data':{group:'Onboard',step:'Step 3 of 4',title:'Extract',text:'Run a saved prompt over indexed documents and compare the extracted fields side by side.'},
 'Extract':{group:'Onboard',step:'Step 4 of 4',title:'Review',text:'Check extracted fields against the source before they are trusted in answers and exports.'},
 'Model Registration':{group:'Settings',title:'Model registration',text:'Register chat, extraction, embedding and OCR models and test their connections.'},
 'Model Mapping':{group:'Settings',title:'Model mapping',text:'Choose which models each collection uses for embedding, chat, extraction and OCR.'},
 'Enabled models':{group:'Settings',title:'Enabled models',text:'Turn registered models on or off for chat and new work, from a computer or a phone.'},
 'Users & passwords':{group:'Settings',title:'Users & passwords',text:'Manage people, roles and collection access, and change your own password.'},
 'Access map':{group:'Settings',title:'Access map',text:'See who can open which collection as a graph, change it in one place, and check that OpenFGA agrees.'},
 'Jobs & activity':{group:'Settings',title:'Jobs & activity',text:'Indexing, extraction and cleanup run in the background. Follow their progress and retry failures here.'},
 'Storage':{group:'Settings',title:'Storage',text:'See where originals, databases and knowledge are kept, and configure file storage.'},
 'Token usage':{group:'Settings',title:'Token usage',text:'Tokens each provider reported for every model call, with approximate cost by collection, model, user and day.'},
 'Files & processing':{group:'Settings',title:'Files & processing',text:"Review every source file's storage, indexing, OCR and extraction status."},
 'Skills & memory':{group:'Lapi Agent',title:'Skills & memory',text:'Teach the agent playbooks, set how it answers for each collection, tune model guides and manage what it remembers about you.'},
 'About':{group:'Lapi',title:'About Lapi',text:'What Lapi does, how it keeps knowledge grounded, and what changed in each version.'},
};

/** Brand band at the top of a screen. The page h1 already names the screen, so the large title is visual only. */
export function PageBand({view}:{view:string}){
 const intro=PAGE_INTROS[view];
 if(!intro)return null;
 return <section className="page-band" aria-label={`${intro.title} overview`}>
  <div className="page-band-copy">
   <span className="page-band-eyebrow">{intro.group}{intro.step?` · ${intro.step}`:''}</span>
   <p className="page-band-title" aria-hidden="true">{intro.title}</p>
   <p className="page-band-text">{intro.text}</p>
  </div>
 </section>;
}
