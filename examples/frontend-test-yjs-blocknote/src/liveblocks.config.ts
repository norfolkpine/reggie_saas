declare global {
  interface UserMeta {
    id: string; // Accessible through `user.id`
    info: {
      name: string;
      color: string;
      picture: string;
    }; // Accessible through `user.info`
    };
  }


export {};
