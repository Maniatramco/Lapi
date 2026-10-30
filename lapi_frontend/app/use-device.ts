"use client";
import {useEffect,useState} from 'react';
import {deviceFor,type Device} from './screens-client';

/** Phone or computer for this window, updated when it is resized across the 640 px breakpoint. */
export function useDevice():Device{
 const [device,setDevice]=useState<Device>(typeof window==='undefined'?'computer':deviceFor(window.innerWidth));
 useEffect(()=>{
  if(typeof window==='undefined'||typeof window.addEventListener!=='function')return;
  const resized=()=>setDevice(deviceFor(window.innerWidth));resized();window.addEventListener('resize',resized);return()=>window.removeEventListener('resize',resized);
 },[]);
 return device;
}
